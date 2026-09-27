"""Geração dos gráficos em SVG no estilo do arquivo de referência
(``ManchesterCityFC_League_Performance.svg``): faixas horizontais por divisão,
linha de desempenho por temporada e rótulos à direita.

Optou-se por SVG puro (sem bibliotecas de plotagem): o resultado fica fiel à
referência, funciona com qualquer tema do Streamlit e ainda oferece dicas
nativas (``<title>``) ao passar o mouse.
"""

from __future__ import annotations

import html
from typing import Iterable, Mapping, Sequence

import pandas as pd

SERIES_ORDEM: tuple[str, ...] = ("A", "B", "C", "D")

#: Base de cada divisão na pirâmide do futebol brasileiro.
BASE_NIVEL: dict[str, int] = {"A": 1, "B": 21, "C": 41, "D": 61}

#: Cinzas das faixas (do topo para baixo), no espírito do SVG de referência.
CINZAS_BANDA: dict[str, str] = {
    "A": "#b8b8b8",
    "B": "#a0a0a0",
    "C": "#888888",
    "D": "#707070",
}

#: Cores das linhas por divisão.
CORES_SERIE: dict[str, str] = {
    "A": "#0b6e4f",
    "B": "#1565c0",
    "C": "#ef6c00",
    "D": "#c62828",
}

#: Símbolos por divisão (diferenciam as séries quando a cor é do clube).
SIMBOLOS_SERIE: dict[str, str] = {
    "A": "circulo",
    "B": "quadrado",
    "C": "triangulo",
    "D": "losango",
}

CORES_CLUBES: tuple[str, ...] = (
    "#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#17becf",
    "#8c564b", "#e377c2", "#bcbd22", "#5254a3", "#ad494a", "#3b3b98",
    "#b8860b", "#00695c", "#6a1b9a", "#bf360c", "#283593", "#00838f",
)

FONTE = "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"


def _esc(texto: object) -> str:
    return html.escape(str(texto), quote=True)


def _rotulo_serie(serie: str) -> str:
    return f"Série {serie}"


def _cabecalho(titulo: str, subtitulo: str, largura: float) -> str:
    partes = [
        f'<text x="{largura / 2:.1f}" y="30" text-anchor="middle" font-family="{FONTE}" '
        f'font-size="23" font-weight="700" fill="#111">{_esc(titulo)}</text>'
    ]
    if subtitulo:
        partes.append(
            f'<text x="{largura / 2:.1f}" y="50" text-anchor="middle" font-family="{FONTE}" '
            f'font-size="12" fill="#555">{_esc(subtitulo)}</text>'
        )
    return "".join(partes)


def _legenda_cores(x: float, y: float, itens: Sequence[tuple[str, str]]) -> str:
    partes: list[str] = []
    desloc = 0.0
    for rotulo, cor in itens:
        partes.append(
            f'<rect x="{x + desloc:.1f}" y="{y - 9:.1f}" width="12" height="10" rx="2" '
            f'fill="{cor}"/>'
        )
        partes.append(
            f'<text x="{x + desloc + 17:.1f}" y="{y:.1f}" font-family="{FONTE}" font-size="11" '
            f'fill="#333">{_esc(rotulo)}</text>'
        )
        desloc += 29 + 7.0 * len(str(rotulo))
    return "".join(partes)


def _marcador(x: float, y: float, simbolo: str, cor: str, tamanho: float = 4.0) -> str:
    """Marcador do ponto, na forma correspondente à divisão."""
    t = tamanho
    if simbolo == "quadrado":
        return (
            f'<rect x="{x - t:.2f}" y="{y - t:.2f}" width="{2 * t:.2f}" height="{2 * t:.2f}" '
            f'fill="{cor}" stroke="#fff" stroke-width="1.2"/>'
        )
    if simbolo == "triangulo":
        return (
            f'<polygon points="{x:.2f},{y - t * 1.3:.2f} {x - t * 1.2:.2f},{y + t:.2f} '
            f'{x + t * 1.2:.2f},{y + t:.2f}" fill="{cor}" stroke="#fff" stroke-width="1.2"/>'
        )
    if simbolo == "losango":
        return (
            f'<polygon points="{x:.2f},{y - t * 1.35:.2f} {x + t * 1.35:.2f},{y:.2f} '
            f'{x:.2f},{y + t * 1.35:.2f} {x - t * 1.35:.2f},{y:.2f}" fill="{cor}" '
            f'stroke="#fff" stroke-width="1.2"/>'
        )
    return (
        f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{t:.2f}" fill="{cor}" stroke="#fff" '
        f'stroke-width="1.2"/>'
    )


def _empilhar_rotulos(
    valores: Sequence[tuple[str, float]], minimo: float, maximo: float, passo: float = 16.0
) -> list[tuple[str, float]]:
    """Afasta rótulos sobrepostos e mantém todos dentro dos limites verticais."""
    if not valores:
        return []
    itens = sorted(valores, key=lambda par: par[1])
    ajustados: list[tuple[str, float]] = []
    for rotulo, y in itens:
        if ajustados:
            y = max(y, ajustados[-1][1] + passo)
        ajustados.append((rotulo, y))
    excesso = ajustados[-1][1] - maximo
    if excesso > 0:
        ajustados = [(r, y - excesso) for r, y in ajustados]
    if ajustados[0][1] < minimo:
        desloc = minimo - ajustados[0][1]
        ajustados = [(r, y + desloc) for r, y in ajustados]
    return ajustados


def _maior_n_clubes(dados: pd.DataFrame, serie: str, padrao: int = 20) -> int:
    """Maior número de clubes de uma série no recorte (robusto a séries vazias)."""
    valores = dados.loc[dados["serie"] == serie, "n_clubes"]
    if valores.empty:
        return padrao
    maximo = valores.max()
    if pd.isna(maximo):
        return padrao
    return max(2, int(maximo))


def _svg_vazio(titulo: str, mensagem: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="200" viewBox="0 0 900 200" '
        f'font-family="{FONTE}">'
        '<rect width="900" height="200" fill="#ffffff"/>'
        f'<text x="450" y="70" text-anchor="middle" font-size="19" font-weight="700" '
        f'fill="#111">{_esc(titulo)}</text>'
        f'<text x="450" y="108" text-anchor="middle" font-size="14" fill="#666">'
        f"{_esc(mensagem)}</text></svg>"
    )


def grafico_desempenho(
    df: pd.DataFrame,
    *,
    titulo: str,
    subtitulo: str = "",
    colorir_por: str = "serie",
    series: Iterable[str] = SERIES_ORDEM,
    escala_clubes: str = "por_ano",
    cores_clubes: Mapping[str, str] | None = None,
    referencia: pd.DataFrame | None = None,
    altura: int = 620,
) -> str:
    """SVG de desempenho (posição por temporada) de um ou mais clubes.

    Args:
        df: subconjunto com ``ano``, ``serie``, ``posicao``, ``clube``,
            ``clube_id``, ``n_clubes`` e ``indice_temporada``.
        colorir_por: ``"serie"`` (a cor indica a divisão) ou ``"clube"``.
        series: divisões que devem aparecer como faixas.
        escala_clubes: ``"por_ano"`` usa o número de clubes de cada edição;
            ``"fixa"`` usa o maior número de clubes da divisão no período,
            deixando as posições comparáveis entre temporadas.
        referencia: recorte maior (sem o filtro de clubes) usado para calcular
            a escala das faixas. Evita que a escala mude de um clube para outro.
    """
    series_exibidas = [s for s in SERIES_ORDEM if s in set(series)]
    if df.empty or not series_exibidas:
        return _svg_vazio(titulo, "Sem dados para os filtros selecionados.")

    dados = df[df["serie"].isin(series_exibidas)].copy()
    if dados.empty:
        return _svg_vazio(titulo, "Sem dados para os filtros selecionados.")

    escala_fonte = referencia if referencia is not None and not referencia.empty else dados
    escala_fonte = escala_fonte[escala_fonte["serie"].isin(series_exibidas)]

    anos = sorted(int(a) for a in dados["ano"].unique())
    ano_min = anos[0]
    passo = max(18.0, min(46.0, 1180.0 / max(1, len(anos))))
    margem_esq, margem_dir = 80.0, 260.0
    largura = margem_esq + passo * max(1, len(anos) - 1) + margem_dir
    topo, altura_eixo = 72.0, 108.0
    base = altura - altura_eixo
    altura_plot = base - topo
    altura_banda = altura_plot / len(series_exibidas)
    largura_faixa = largura - margem_esq - margem_dir

    if escala_clubes == "fixa":
        base_clubes = {s: _maior_n_clubes(escala_fonte, s) for s in series_exibidas}
    else:
        base_clubes = {s: 20 for s in series_exibidas}

    def x_de(ano: int) -> float:
        return margem_esq + (ano - ano_min) * passo

    def y_de(serie: str, posicao: int, n_clubes: int) -> float:
        topo_banda = topo + series_exibidas.index(serie) * altura_banda
        referencia = base_clubes[serie] if escala_clubes == "fixa" else max(2, n_clubes)
        fracao = (posicao - 1) / max(1, referencia - 1)
        recuo = 12.0
        return topo_banda + recuo + min(1.0, fracao) * (altura_banda - 2 * recuo)

    partes: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{largura:.0f}" height="{altura}" '
        f'viewBox="0 0 {largura:.0f} {altura}" font-family="{FONTE}">',
        f'<rect width="{largura:.0f}" height="{altura}" fill="#ffffff"/>',
        _cabecalho(titulo, subtitulo, largura),
    ]

    # ---------------------------------------------------------------- faixas
    direita_faixa = margem_esq + largura_faixa
    for i, serie in enumerate(series_exibidas):
        y0 = topo + i * altura_banda
        partes.append(
            f'<rect x="{margem_esq:.1f}" y="{y0:.1f}" width="{largura_faixa:.1f}" '
            f'height="{altura_banda:.1f}" fill="{CINZAS_BANDA[serie]}"/>'
        )
        rotulo = _rotulo_serie(serie)
        largura_rotulo = 9.4 * len(rotulo) + 20
        centro = y0 + altura_banda / 2
        partes.append(
            f'<rect x="{direita_faixa - largura_rotulo - 10:.1f}" y="{centro - 15:.1f}" '
            f'width="{largura_rotulo:.1f}" height="26" rx="5" fill="#000000" '
            f'fill-opacity="0.16"/>'
            f'<text x="{direita_faixa - 20:.1f}" y="{centro + 6:.1f}" text-anchor="end" '
            f'font-size="17" font-weight="700" fill="#ffffff">{_esc(rotulo)}</text>'
        )

    # ------------------------------------------------- grade e eixo de tempo
    rotulo_cada = max(1, len(anos) // 30 + 1)
    for i, ano in enumerate(anos):
        x = x_de(ano)
        partes.append(
            f'<line x1="{x:.1f}" y1="{topo:.1f}" x2="{x:.1f}" y2="{base:.1f}" stroke="#000" '
            f'stroke-opacity="0.08" stroke-width="1"/>'
        )
        if i % rotulo_cada == 0 or i == len(anos) - 1:
            partes.append(
                f'<line x1="{x:.1f}" y1="{base:.1f}" x2="{x:.1f}" y2="{base + 6:.1f}" '
                f'stroke="#666" stroke-width="1"/>'
            )
            partes.append(
                f'<text transform="rotate(-90 {x + 4:.1f} {base + 14:.1f})" x="{x + 4:.1f}" '
                f'y="{base + 14:.1f}" font-size="11" fill="#333">{ano}</text>'
            )
    partes.append(
        f'<text x="{margem_esq + largura_faixa / 2:.1f}" y="{altura - 24:.1f}" '
        f'text-anchor="middle" font-size="13" font-weight="600" fill="#333">Temporada</text>'
    )

    # escala de posições (referência da faixa superior)
    primeira = series_exibidas[0]
    n_ref = base_clubes[primeira] if escala_clubes == "fixa" else _maior_n_clubes(escala_fonte, primeira)
    for marca in (1, 2, 5, 10, 15, 20):
        if marca > n_ref:
            continue
        y = y_de(primeira, marca, n_ref)
        partes.append(
            f'<text x="{margem_esq - 10:.1f}" y="{y + 4:.1f}" text-anchor="end" font-size="11" '
            f'fill="#333">{marca}º</text>'
        )
    partes.append(
        '<text transform="rotate(-90 26 300)" x="26" y="300" text-anchor="middle" font-size="13" '
        'font-weight="600" fill="#333">Posição</text>'
    )

    # ----------------------------------------------------------------- linhas
    clubes = list(dict.fromkeys(dados["clube"].tolist()))
    mapa_cores = {
        clube: (
            cores_clubes[clube]
            if cores_clubes and clube in cores_clubes
            else CORES_CLUBES[i % len(CORES_CLUBES)]
        )
        for i, clube in enumerate(clubes)
    }

    def cor_de(clube: str, serie: str) -> str:
        return mapa_cores[clube] if colorir_por == "clube" else CORES_SERIE[serie]

    rotulos_finais: list[tuple[str, float]] = []
    for clube in clubes:
        sub = dados[dados["clube"] == clube].sort_values("ano")
        pontos: list[tuple[int, float, float, str, int, float]] = []
        for linha in sub.itertuples(index=False):
            ano = int(linha.ano)
            serie = str(linha.serie)
            posicao = int(linha.posicao)
            n_clubes = int(linha.n_clubes)
            pontos.append(
                (
                    ano,
                    x_de(ano),
                    y_de(serie, posicao, n_clubes),
                    serie,
                    posicao,
                    float(linha.indice_temporada),
                )
            )

        for anterior, atual in zip(pontos, pontos[1:]):
            ano1, x1, y1, s1, p1, _ = anterior
            ano2, x2, y2, s2, p2, _ = atual
            if ano2 - ano1 > 1:
                continue  # não participou em algum ano: interrompe a linha
            dica = f"{clube}: {s1} {ano1} ({p1}º) → {s2} {ano2} ({p2}º)"
            if s1 == s2:
                trechos = [(x1, y1, x2, y2, s1)]
            else:
                xm, ym = (x1 + x2) / 2, (y1 + y2) / 2
                trechos = [(x1, y1, xm, ym, s1), (xm, ym, x2, y2, s2)]
            for xa, ya, xb, yb, serie_trecho in trechos:
                partes.append(
                    f'<g><title>{_esc(dica)}</title><line x1="{xa:.1f}" y1="{ya:.1f}" '
                    f'x2="{xb:.1f}" y2="{yb:.1f}" stroke="{cor_de(clube, serie_trecho)}" '
                    f'stroke-width="2.6" stroke-linecap="round"/></g>'
                )

        for ano, x, y, serie, posicao, indice in pontos:
            dica = (
                f"{clube} — {ano}: {_rotulo_serie(serie)}, {posicao}º lugar "
                f"(índice {indice:.1f})"
            )
            partes.append(
                f'<g><title>{_esc(dica)}</title>'
                f"{_marcador(x, y, SIMBOLOS_SERIE[serie], cor_de(clube, serie))}</g>"
            )

        if pontos:
            rotulos_finais.append((clube, pontos[-1][2]))

    for clube, y in _empilhar_rotulos(rotulos_finais, topo + 8, base - 6):
        ultimo = dados[dados["clube"] == clube].sort_values("ano").iloc[-1]
        cor = cor_de(clube, str(ultimo["serie"]))
        partes.append(
            f'<rect x="{largura - margem_dir + 6:.1f}" y="{y - 6:.1f}" width="10" height="10" '
            f'rx="2" fill="{cor}"/>'
        )
        partes.append(
            f'<text x="{largura - margem_dir + 22:.1f}" y="{y + 3:.1f}" font-size="12.5" '
            f'fill="#111">{_esc(clube)}</text>'
        )

    if colorir_por == "serie":
        itens = [(_rotulo_serie(s), CORES_SERIE[s]) for s in series_exibidas]
    else:
        itens = [(clube, mapa_cores[clube]) for clube in clubes[:10]]
    partes.append(_legenda_cores(margem_esq, altura - 6, itens))
    partes.append("</svg>")
    return "".join(partes)


def grafico_ranking(
    tabela: pd.DataFrame,
    *,
    titulo: str,
    subtitulo: str = "",
    limite: int = 25,
) -> str:
    """Barras horizontais com os clubes mais bem colocados no ranking.

    O maior índice fica no topo: as barras são desenhadas de cima para baixo na
    ordem decrescente do índice.
    """
    if tabela.empty:
        return _svg_vazio(titulo, "Sem dados para os filtros selecionados.")

    dados = (
        tabela.sort_values("indice", ascending=False)
        .head(limite)
        .reset_index(drop=True)
    )
    altura_linha = 26.0
    margem_topo, margem_base, margem_esq, margem_dir = 78.0, 36.0, 260.0, 80.0
    altura = margem_topo + margem_base + altura_linha * len(dados)
    largura = 1000.0
    largura_barra = largura - margem_esq - margem_dir
    maximo = float(dados["indice"].max()) or 1.0

    partes: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{largura:.0f}" height="{altura:.0f}" '
        f'viewBox="0 0 {largura:.0f} {altura:.0f}" font-family="{FONTE}">',
        f'<rect width="{largura:.0f}" height="{altura:.0f}" fill="#ffffff"/>',
        f'<text x="{largura / 2:.0f}" y="32" text-anchor="middle" font-size="21" '
        f'font-weight="700" fill="#111">{_esc(titulo)}</text>',
    ]
    if subtitulo:
        partes.append(
            f'<text x="{largura / 2:.0f}" y="52" text-anchor="middle" font-size="12" '
            f'fill="#555">{_esc(subtitulo)}</text>'
        )

    for i, linha in dados.iterrows():
        y = margem_topo + i * altura_linha
        largura_atual = largura_barra * float(linha["indice"]) / maximo
        serie = max(
            ((s, int(linha[s])) for s in SERIES_ORDEM if s in linha.index),
            key=lambda par: par[1],
            default=("A", 0),
        )[0]
        cor = CORES_SERIE[serie]
        dica = (
            f"{linha['clube']} · índice {float(linha['indice']):.1f} · "
            f"{int(linha['participacoes'])} participações · {int(linha['titulos'])} título(s) · "
            f"melhor {int(linha['melhor'])}º"
        )
        partes.append(
            f'<g><title>{_esc(dica)}</title>'
            f'<rect x="{margem_esq:.1f}" y="{y + 4:.1f}" width="{largura_barra:.1f}" '
            f'height="{altura_linha - 9:.1f}" rx="3" fill="#f1f1f1"/>'
            f'<rect x="{margem_esq:.1f}" y="{y + 4:.1f}" width="{max(2.0, largura_atual):.2f}" '
            f'height="{altura_linha - 9:.1f}" rx="3" fill="{cor}"/>'
            f'<text x="{margem_esq - 12:.1f}" y="{y + altura_linha / 2 + 4:.1f}" text-anchor="end" '
            f'font-size="12.5" fill="#111">{_esc(linha["clube"])}</text>'
            f'<text x="{margem_esq + max(2.0, largura_atual) + 8:.1f}" '
            f'y="{y + altura_linha / 2 + 4:.1f}" font-size="12" fill="#333">'
            f"{float(linha['indice']):.1f}</text></g>"
        )

    partes.append(
        _legenda_cores(
            margem_esq, altura - 12, [(_rotulo_serie(s), CORES_SERIE[s]) for s in SERIES_ORDEM]
        )
    )
    partes.append(
        f'<text x="{largura - 10:.1f}" y="{margem_topo - 14:.1f}" text-anchor="end" font-size="12" '
        f'fill="#555">Índice de desempenho acumulado</text>'
    )
    partes.append("</svg>")
    return "".join(partes)
