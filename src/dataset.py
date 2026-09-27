"""Monta e mantém o conjunto de dados consolidado das classificações."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence

import pandas as pd

from . import scraper
from .clubs import CatalogoClubes

#: Peso de cada série no índice de desempenho (Série A vale mais).
PESOS_PADRAO: dict[str, float] = {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0}

#: Colunas de estatística na ordem em que aparecem nas tabelas.
_COLUNAS_ESTAT = ["pontos", "jogos", "vitorias", "empates", "derrotas", "gp", "gc", "sg"]

BASE_ABSOLUTA: dict[str, int] = {"A": 1, "B": 21, "C": 41, "D": 61}

COLUNAS = [
    "ano",
    "serie",
    "posicao",
    "clube_id",
    "clube",
    "uf",
    "n_clubes",
    "posicao_absoluta",
    "indice_temporada",
    *(_COLUNAS_ESTAT),
]


def construir_dataframe(registros: Sequence[scraper.Classificacao]) -> pd.DataFrame:
    """Converte os registros coletados num ``DataFrame`` normalizado."""
    catalogo = CatalogoClubes((r.ano, r.serie, r.clube_bruto, r.imagens) for r in registros)
    linhas: list[dict] = []
    for r in registros:
        clube_id, uf, exibicao = catalogo.identificar(
            r.clube_bruto, r.serie, r.ano, r.imagens
        )
        linha = {
            "ano": r.ano,
            "serie": r.serie,
            "posicao": r.posicao,
            "clube_id": clube_id,
            "clube": exibicao,
            "uf": uf,
            "posicao_absoluta": BASE_ABSOLUTA[r.serie] + r.posicao - 1,
        }
        valores = r.estatisticas
        for nome, valor in zip(_COLUNAS_ESTAT, valores):
            linha[nome] = int(valor)
        linhas.append(linha)

    if not linhas:
        return pd.DataFrame(columns=COLUNAS)

    df = pd.DataFrame(linhas)
    for coluna in _COLUNAS_ESTAT:
        if coluna not in df.columns:
            df[coluna] = pd.NA
        df[coluna] = pd.to_numeric(df[coluna], errors="coerce").astype("Int64")

    df["n_clubes"] = df.groupby(["ano", "serie"])["posicao"].transform("size").astype(int)

    # O site publica, para a edição em andamento, apenas a lista de participantes
    # (nomes em ordem alfabética, sem resultados). Essas edições são descartadas.
    sem_resultado = df.groupby(["ano", "serie"])["jogos"].transform("max").fillna(0) <= 0
    ignoradas = sorted(
        (int(ano), str(serie))
        for ano, serie in df.loc[sem_resultado, ["ano", "serie"]].drop_duplicates().itertuples(index=False)
    )
    df = df[~sem_resultado].copy()
    if df.empty:
        resultado = pd.DataFrame(columns=COLUNAS)
        resultado.attrs["edicoes_ignoradas"] = ignoradas
        return resultado

    # Um clube pode aparecer em duas tabelas da mesma edição (empates/playoffs);
    # mantém-se a melhor posição.
    df = (
        df.sort_values(["ano", "serie", "posicao"])
        .drop_duplicates(subset=["ano", "serie", "clube_id"], keep="first")
        .reset_index(drop=True)
    )
    df["n_clubes"] = df.groupby(["ano", "serie"])["posicao"].transform("size").astype(int)
    df["indice_temporada"] = aplicar_indice(df, PESOS_PADRAO)

    # Nome de exibição mais frequente para cada clube.
    padrao = (
        df.groupby(["clube_id", "clube"]).size().reset_index(name="n")
        .sort_values("n", ascending=False)
        .drop_duplicates("clube_id")
        .set_index("clube_id")["clube"]
    )
    df["clube"] = df["clube_id"].map(padrao)

    df = df[[c for c in COLUNAS if c in df.columns]].sort_values(
        ["ano", "serie", "posicao"]
    ).reset_index(drop=True)
    df.attrs["edicoes_ignoradas"] = ignoradas
    return df


def aplicar_indice(df: pd.DataFrame, pesos: Mapping[str, float]) -> pd.Series:
    """Índice de desempenho de cada campanha, na escala 0-100 por série.

    ``indice = peso_serie * (n_clubes - posicao + 1) / n_clubes * 100``
    """
    peso = df["serie"].map(pesos).astype(float)
    fator = (df["n_clubes"] - df["posicao"] + 1) / df["n_clubes"]
    return (peso * fator * 100).round(2)


def ranking(df: pd.DataFrame, pesos: Mapping[str, float] | None = None) -> pd.DataFrame:
    """Ranking histórico dos clubes a partir das campanhas carregadas."""
    if df.empty:
        return pd.DataFrame(
            columns=["clube_id", "clube", "uf", "participacoes", "indice", "melhor", "series"]
        )
    base = df.copy()
    base["indice_temporada"] = aplicar_indice(base, pesos or PESOS_PADRAO)
    agrupado = (
        base.groupby(["clube_id", "clube", "uf"], dropna=False)
        .agg(
            participacoes=("ano", "size"),
            indice=("indice_temporada", "sum"),
            melhor=("posicao_absoluta", "min"),
            primeira=("ano", "min"),
            ultima=("ano", "max"),
            titulos=("posicao", lambda s: int((s == 1).sum())),
        )
        .reset_index()
    )
    por_serie = (
        base.groupby(["clube_id", "serie"]).size().unstack(fill_value=0)
    )
    for serie in scraper.SERIES:
        if serie not in por_serie.columns:
            por_serie[serie] = 0
    por_serie = por_serie[[*scraper.SERIES]]
    agrupado = agrupado.merge(
        por_serie, left_on="clube_id", right_index=True, how="left"
    )
    agrupado["indice"] = agrupado["indice"].round(1)
    return agrupado.sort_values("indice", ascending=False).reset_index(drop=True)


def salvar(df: pd.DataFrame, caminho: Path) -> None:
    """Grava o conjunto de dados em CSV."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(caminho, index=False, encoding="utf-8")


def carregar(caminho: Path) -> pd.DataFrame:
    """Lê o conjunto de dados do CSV e recompõe os tipos."""
    df = pd.read_csv(caminho, encoding="utf-8")
    for coluna in _COLUNAS_ESTAT + ["n_clubes"]:
        if coluna in df.columns:
            df[coluna] = pd.to_numeric(df[coluna], errors="coerce").astype("Int64")
    return df


def atualizar(
    csv_path: Path,
    raw_dir: Path,
    series: Iterable[str] = scraper.SERIES,
    ate: int | None = None,
    forcar: bool = False,
    intervalo: float = 0.3,
    progresso: scraper.Progresso | None = None,
) -> pd.DataFrame:
    """Coleta, consolida e grava o conjunto de dados."""
    registros = scraper.coletar(
        raw_dir,
        series=series,
        ate=ate,
        forcar=forcar,
        intervalo=intervalo,
        progresso=progresso,
    )
    df = construir_dataframe(registros)
    salvar(df, csv_path)
    return df


def carregar_ou_atualizar(
    csv_path: Path,
    raw_dir: Path,
    forcar: bool = False,
    progresso: scraper.Progresso | None = None,
) -> pd.DataFrame:
    """Usa o CSV local; se não existir (ou ``forcar``), coleta do site."""
    if csv_path.exists() and not forcar:
        return carregar(csv_path)
    return atualizar(csv_path, raw_dir, forcar=forcar, progresso=progresso)
