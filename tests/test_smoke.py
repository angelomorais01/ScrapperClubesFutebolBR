#!/usr/bin/env python3
"""Verificações rápidas do projeto (offline, sem rede).

Uso::

    python tests/test_smoke.py          # ou: pytest tests/test_smoke.py

Cobre:

* o parser de tabelas, com um HTML de exemplo no formato do site;
* a normalização de nomes/UF dos clubes;
* o índice de desempenho e o ranking;
* a geração de SVG para todos os clubes do CSV local, em todas as combinações
  de escala e coloração (garante que nenhum clube quebra o gráfico).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src import charts, clubs, dataset, scraper  # noqa: E402

CSV = RAIZ / "data" / "brasileirao.csv"

HTML_EXEMPLO = """
<html><body>
<table border="0"><tr>
  <td>CLUBES</td><td>PG</td><td>J</td><td>V</td><td>E</td><td>D</td><td>GP</td><td>GC</td><td>SG</td>
</tr>
<tr>
  <td><font color="#008000">1º</font> Atlético (PR)</td>
  <td>63</td><td>31</td><td>19</td><td>6</td><td>6</td><td>68</td><td>45</td><td>23</td>
</tr>
<tr>
  <td>2º São Caetano (SP)</td>
  <td>63</td><td>31</td><td>19</td><td>6</td><td>6</td><td>52</td><td>31</td><td>21</td>
</tr>
<tr>
  <td>3º</td><td>Fluminense (RJ)</td>
  <td>54</td><td>29</td><td>15</td><td>9</td><td>5</td><td>49</td><td>34</td><td>15</td>
</tr>
<tr>
  <td>4º</td><td>Atlético (MG)</td>
  <td>52</td><td>29</td><td>16</td><td>4</td><td>9</td><td>54</td><td>36</td><td>18</td>
</tr>
<tr>
  <td>5º</td><td>Grêmio (RS)</td>
  <td>47</td><td>28</td><td>14</td><td>5</td><td>9</td><td>39</td><td>32</td><td>7</td>
</tr>
<tr>
  <td>6º</td><td>Ponte Preta (SP)</td>
  <td>47</td><td>28</td><td>13</td><td>8</td><td>7</td><td>55</td><td>51</td><td>4</td>
</tr>
<tr>
  <td>7º</td><td>São Paulo (SP)</td>
  <td>46</td><td>28</td><td>13</td><td>7</td><td>8</td><td>49</td><td>36</td><td>13</td>
</tr>
<tr>
  <td>8º</td><td>Bahia (BA)</td>
  <td>46</td><td>28</td><td>13</td><td>7</td><td>8</td><td>43</td><td>38</td><td>5</td>
</tr>
</table>
<table><tr><td>1</td><td>Maior número de vitórias</td></tr></table>
</body></html>
"""

HTML_PLACEHOLDER = """
<html><body><table>
<tr><td>P</td><td>FINALISTAS</td><td>PG</td><td>J</td><td>V</td></tr>
<tr><td>1º</td><td>.</td><td>..</td><td>0</td><td>0</td><td>0</td></tr>
<tr><td>2º</td><td>.</td><td>..</td><td>0</td><td>0</td><td>0</td></tr>
</table></body></html>
"""


def teste_parser_identifica_classificacao() -> None:
    linhas = scraper.extrair_classificacao(HTML_EXEMPLO)
    assert [linha.posicao for linha in linhas] == [1, 2, 3, 4, 5, 6, 7, 8], linhas
    assert linhas[0].clube_bruto == "Atlético (PR)"
    assert linhas[2].clube_bruto == "Fluminense (RJ)"  # posição e clube em células separadas
    assert linhas[0].estatisticas[:3] == ["63", "31", "19"]


def teste_parser_ignora_edicao_sem_nomes() -> None:
    assert scraper.extrair_classificacao(HTML_PLACEHOLDER) == []


def teste_separacao_de_uf() -> None:
    assert clubs.separar_uf("Atlético (PR)") == ("Atlético", "PR")
    assert clubs.separar_uf("Botafogo-PB") == ("Botafogo", "PB")
    assert clubs.separar_uf("Vasco (RJ)*") == ("Vasco", "RJ")
    assert clubs.separar_uf("Mirassol") == ("Mirassol", None)
    assert clubs.separar_uf("Santos AP") == ("Santos", "AP")


def teste_uf_pelo_escudo() -> None:
    assert clubs.uf_do_escudo(["cb_vitoria-es-2.gif"]) == "ES"
    assert clubs.uf_do_escudo(["cb_pontepreta.gif"]) is None
    assert clubs.uf_do_escudo(["cb_abc-rn.gif", "cb_abc-rn-mini-1.gif"]) == "RN"
    assert clubs.uf_do_escudo(["cb_time-sp.gif", "cb_time-rj.gif"]) is None


def teste_aliases_unificam_grafias() -> None:
    assert clubs.normalizar("Athletico") == clubs.normalizar("Atlético")
    assert clubs.normalizar("Athletico Paranaense") == clubs.normalizar("Atlético")
    assert clubs.normalizar("Sport Recife") == clubs.normalizar("Sport")
    assert clubs.normalizar("Grêmio Barueri") == clubs.normalizar("Barueri")
    assert clubs.formatar_nome("VILA NOVA") == "Vila Nova"
    assert clubs.formatar_nome("REMO") == "Remo"
    assert clubs.formatar_nome("4 DE JULHO") == "4 de Julho"
    assert clubs.formatar_nome("CSA") == "CSA"
    assert clubs.formatar_nome("SÃO JOSÉ") == "São José"


def teste_athletico_e_atletico_pr_sao_o_mesmo_clube() -> None:
    """O Athletico Paranaense mudou de nome: tem de ser um clube só."""
    linhas = [
        (2011, "A", "Atlético (PR)"),
        (2018, "A", "Atlético (PR)"),
        (2019, "A", "Athletico (PR)"),
        (2022, "A", "Athletico Paranaense (PR)"),
    ]
    catalogo = clubs.CatalogoClubes([(ano, serie, bruto, []) for ano, serie, bruto in linhas])
    ids = {catalogo.identificar(bruto, serie, ano)[0] for ano, serie, bruto in linhas}
    assert ids == {"ATLETICO|PR"}, ids
    # o rótulo passa a ser o nome atual do clube
    for ano, serie, bruto in linhas:
        assert catalogo.identificar(bruto, serie, ano)[2] == "Athletico Paranaense (PR)"

    # e os outros Atléticos (MG, GO, BA...) não são afetados
    for uf, esperado in (("MG", "Atlético (MG)"), ("GO", "Atlético (GO)")):
        _, _, exibicao = catalogo.identificar(f"Atlético ({uf})", "A", 2019)
        assert exibicao == esperado, exibicao
    assert catalogo.identificar("Atlético (MG)", "A", 2019)[0] == "ATLETICO|MG"


def teste_indice_e_ranking() -> None:
    df = _carregar()
    if df is None:
        return
    linhas = df[(df["ano"] == 2024) & (df["serie"] == "A") & (df["posicao"] == 1)]
    assert len(linhas) == 1
    # campeão da Série A: peso 4 e fator máximo -> 400
    assert abs(float(linhas.iloc[0]["indice_temporada"]) - 400.0) < 0.01

    rk = dataset.ranking(df)
    assert rk["indice"].is_monotonic_decreasing
    assert rk.iloc[0]["participacoes"] >= 20
    assert set(["A", "B", "C", "D"]).issubset(rk.columns)


def teste_2025_presente_em_todas_as_series() -> None:
    df = _carregar()
    if df is None:
        return
    for serie in ("A", "B", "C", "D"):
        assert (df["ano"] == 2025).sum() > 0, "2025 ausente da base"
        assert ((df["ano"] == 2025) & (df["serie"] == serie)).any(), f"2025/{serie} ausente"


def teste_svg_para_todos_os_clubes() -> None:
    df = _carregar()
    if df is None:
        return
    for clube in df["clube"].unique():
        sub = df[df["clube"] == clube]
        for escala in ("por_ano", "fixa"):
            for colorir in ("serie", "clube"):
                svg = charts.grafico_desempenho(
                    sub,
                    titulo=clube,
                    escala_clubes=escala,
                    colorir_por=colorir,
                    referencia=df,
                )
                assert svg.startswith("<svg") and svg.endswith("</svg>")
    for caso in (df.iloc[0:0], df.head(1), df[df["serie"] == "D"]):
        for escala in ("por_ano", "fixa"):
            charts.grafico_desempenho(caso, titulo="caso-limite", escala_clubes=escala, referencia=df)


def teste_svg_ranking() -> None:
    df = _carregar()
    if df is None:
        return
    rk = dataset.ranking(df)
    for limite in (1, 5, 50):
        assert charts.grafico_ranking(rk, titulo="ranking", limite=limite).endswith("</svg>")
    assert "Sem dados" in charts.grafico_ranking(rk.iloc[0:0], titulo="vazio")

    # o maior índice deve ficar no topo do gráfico (primeiro rótulo desenhado)
    svg = charts.grafico_ranking(rk, titulo="ranking", limite=10)
    rotulos = re.findall(
        r'text-anchor="end" font-size="12\.5" fill="#111">([^<]+)<', svg
    )
    esperado = rk.sort_values("indice", ascending=False).head(10)["clube"].tolist()
    assert rotulos == esperado, f"ordem do gráfico: {rotulos} != {esperado}"

    # e o gráfico não depende da ordem da tabela recebida
    svg_embaralhado = charts.grafico_ranking(
        rk.sort_values("indice").reset_index(drop=True), titulo="ranking", limite=10
    )
    assert re.findall(
        r'text-anchor="end" font-size="12\.5" fill="#111">([^<]+)<', svg_embaralhado
    ) == esperado


def _carregar():
    if not CSV.exists():
        print(f"  (sem {CSV.name}: rode scripts/build_dataset.py para os testes de dados)")
        return None
    return dataset.carregar(CSV)


def main() -> int:
    testes = [v for k, v in sorted(globals().items()) if k.startswith("teste_")]
    falhas = 0
    for teste in testes:
        try:
            teste()
            print(f"OK    {teste.__name__}")
        except AssertionError as erro:
            falhas += 1
            print(f"FALHA {teste.__name__}: {erro}")
        except Exception as erro:  # pragma: no cover
            falhas += 1
            print(f"ERRO  {teste.__name__}: {type(erro).__name__}: {erro}")
    print(f"\n{len(testes) - falhas}/{len(testes)} testes passaram")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
