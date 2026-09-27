"""Aplicação Streamlit: desempenho dos clubes brasileiros nas Séries A, B, C e D.

Execute com::

    streamlit run app.py

Os dados vêm do portal Bola na Área (https://www.bolanaarea.com) e ficam
guardados em ``data/brasileirao.csv``, para que a aplicação funcione offline
depois da primeira coleta.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from src import charts, dataset, scraper
from src.dataset import PESOS_PADRAO

RAIZ = Path(__file__).parent
CSV_DADOS = RAIZ / "data" / "brasileirao.csv"
DIR_BRUTO = RAIZ / "data" / "raw"

st.set_page_config(
    page_title="Ranking de Clubes · Brasileirão",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Carregamento dos dados
# ---------------------------------------------------------------------------
def _coletar(forcar: bool) -> pd.DataFrame:
    """Coleta do site mostrando o andamento na tela."""
    barra = st.progress(0.0, text="Iniciando coleta…")

    def progresso(mensagem: str, atual: int, total: int) -> None:
        barra.progress(atual / total, text=f"Baixando {mensagem} ({atual}/{total})")

    try:
        df = dataset.atualizar(CSV_DADOS, DIR_BRUTO, forcar=forcar, progresso=progresso)
    finally:
        barra.empty()
    return df


@st.cache_data(show_spinner=False)
def carregar_csv(caminho: str, mtime: float) -> pd.DataFrame:
    return dataset.carregar(Path(caminho))


def obter_dados() -> pd.DataFrame:
    if CSV_DADOS.exists():
        return carregar_csv(str(CSV_DADOS), CSV_DADOS.stat().st_mtime)
    st.info("Primeira execução: coletando as classificações no Bola na Área…")
    df = _coletar(forcar=False)
    st.cache_data.clear()
    return df


def svg_bloco(svg: str, altura: int) -> None:
    """Mostra um SVG permitindo rolagem horizontal em telas estreitas."""
    st.iframe(
        '<html><head><meta charset="utf-8"></head><body style="margin:0">'
        '<div style="overflow-x:auto; width:100%;">'
        f'<div style="min-width:760px;">{svg}</div></div></body></html>',
        height=altura + 20,
    )


# ---------------------------------------------------------------------------
# Barra lateral
# ---------------------------------------------------------------------------
df_completo = obter_dados()

st.sidebar.title("⚽ Ranking de Clubes")
st.sidebar.caption(
    "Desempenho dos clubes brasileiros nas Séries A, B, C e D desde 2001 "
    "(Série D desde 2009). Fonte: Bola na Área."
)

if df_completo.empty:
    st.error(
        "Nenhum dado foi carregado. Verifique a conexão com a internet e use "
        "**Atualizar dados do site** na barra lateral."
    )
    st.stop()

anos_disponiveis = sorted(int(a) for a in df_completo["ano"].unique())
ano_min, ano_max = anos_disponiveis[0], anos_disponiveis[-1]

series_rotulos = {s: f"Série {s}" for s in scraper.SERIES}
series_sel = st.sidebar.multiselect(
    "Divisões",
    options=list(scraper.SERIES),
    default=list(scraper.SERIES),
    format_func=lambda s: series_rotulos[s],
)

if len(anos_disponiveis) > 1:
    periodo = st.sidebar.slider(
        "Período",
        min_value=ano_min,
        max_value=ano_max,
        value=(ano_min, ano_max),
        step=1,
    )
else:
    periodo = (ano_min, ano_max)

filtro_base = df_completo[
    df_completo["serie"].isin(series_sel)
    & df_completo["ano"].between(periodo[0], periodo[1])
]

opcoes_clubes = (
    filtro_base.groupby("clube")["ano"].max().sort_values(ascending=False).index.tolist()
)
lider = dataset.ranking(filtro_base, PESOS_PADRAO)
lider_nome = lider.iloc[0]["clube"] if not lider.empty else None
padrao = [lider_nome] if lider_nome in opcoes_clubes else (opcoes_clubes[:1] if opcoes_clubes else [])
clubes_sel = st.sidebar.multiselect(
    "Clubes",
    options=opcoes_clubes,
    default=padrao,
    help="Selecione um clube para ver a trajetória entre as divisões.",
)

if not clubes_sel and opcoes_clubes:
    st.sidebar.info("Nenhum clube selecionado — mostrando o ranking histórico.")

st.sidebar.divider()
colorir_por = st.sidebar.radio(
    "Cor das linhas",
    options=["serie", "clube"],
    format_func=lambda v: "Divisão" if v == "serie" else "Clube",
    horizontal=True,
    help="Com vários clubes selecionados, colorir por clube facilita a leitura.",
)
escala = st.sidebar.radio(
    "Escala das posições",
    options=["por_ano", "fixa"],
    format_func=lambda v: (
        "Proporcional à edição" if v == "por_ano" else "Comparável entre edições"
    ),
    horizontal=False,
)

with st.sidebar.expander("Pesos do índice de desempenho"):
    pesos = {}
    for serie in scraper.SERIES:
        pesos[serie] = st.number_input(
            f"Série {serie}", min_value=0.0, max_value=10.0, value=float(PESOS_PADRAO[serie]),
            step=0.5, key=f"peso_{serie}",
        )
    st.caption(
        "Índice da campanha = peso × (nº de clubes − posição + 1) ÷ nº de clubes × 100."
    )

st.sidebar.divider()
if st.sidebar.button("🔄 Atualizar dados do site", width="stretch"):
    with st.spinner("Baixando as tabelas do Bola na Área…"):
        _coletar(forcar=False)
    st.cache_data.clear()
    st.rerun()

if st.sidebar.button("⬇️ Rebaixar tudo novamente", width="stretch"):
    with st.spinner("Refazendo o download de todas as edições…"):
        _coletar(forcar=True)
    st.cache_data.clear()
    st.rerun()

st.sidebar.download_button(
    "💾 Baixar CSV consolidado",
    data=df_completo.to_csv(index=False).encode("utf-8"),
    file_name="brasileirao_series_A_B_C_D.csv",
    mime="text/csv",
    width="stretch",
)
st.sidebar.caption(
    f"Cada arquivo em `data/raw` guarda a página de uma edição. "
    f"Edições carregadas: {filtro_base['ano'].nunique()}."
)

# ---------------------------------------------------------------------------
# Conteúdo principal
# ---------------------------------------------------------------------------
st.title("Desempenho dos clubes brasileiros no Campeonato Brasileiro")
st.caption(
    "Gráficos no estilo do desempenho do Manchester City (faixas por divisão): "
    "a posição indicada é a colocação final do clube naquela temporada."
)

ranking = dataset.ranking(filtro_base, pesos)
colunas_kpi = st.columns(4)
colunas_kpi[0].metric("Temporadas no recorte", f"{filtro_base['ano'].nunique()}")
colunas_kpi[1].metric("Edições (série × ano)", f"{len(filtro_base.groupby(['ano', 'serie']))}")
colunas_kpi[2].metric("Clubes", f"{filtro_base['clube'].nunique()}")
colunas_kpi[3].metric(
    "Clube líder do índice",
    ranking.iloc[0]["clube"] if not ranking.empty else "—",
)

aba_desempenho, aba_ranking, aba_dados = st.tabs(
    ["📈 Desempenho", "🏆 Ranking histórico", "📋 Dados"]
)

with aba_desempenho:
    if clubes_sel:
        dados_plot = filtro_base[filtro_base["clube"].isin(clubes_sel)]
        cores = {
            clube: charts.CORES_CLUBES[i % len(charts.CORES_CLUBES)]
            for i, clube in enumerate(clubes_sel)
        }
        titulo = (
            clubes_sel[0]
            if len(clubes_sel) == 1
            else f"{len(clubes_sel)} clubes comparados"
        )
        subtitulo = (
            f"{periodo[0]}–{periodo[1]} · "
            f"{', '.join(series_rotulos[s] for s in series_sel)} · "
            "linha interrompida em temporadas sem participação"
        )
        altura = 190 + 118 * len(series_sel)
        svg = charts.grafico_desempenho(
            dados_plot,
            titulo=titulo,
            subtitulo=subtitulo,
            colorir_por=colorir_por,
            series=series_sel,
            escala_clubes=escala,
            cores_clubes=cores,
            referencia=filtro_base,
            altura=altura,
        )
        svg_bloco(svg, altura)

        if len(clubes_sel) == 1:
            detalhe = dados_plot.sort_values("ano")
            st.subheader(f"Campanhas de {clubes_sel[0]}")
            resumo = (
                detalhe.groupby("serie")
                .agg(
                    temporadas=("ano", "size"),
                    primeira=("ano", "min"),
                    ultima=("ano", "max"),
                    melhor=("posicao", "min"),
                    pior=("posicao", "max"),
                    titulos=("posicao", lambda s: int((s == 1).sum())),
                )
                .reindex([s for s in scraper.SERIES if s in set(detalhe["serie"])])
            )
            resumo.index = [f"Série {s}" for s in resumo.index]
            st.dataframe(resumo, width="stretch")
    else:
        svg = charts.grafico_ranking(
            ranking,
            titulo="Índice de desempenho por clube",
            subtitulo=(
                f"{periodo[0]}–{periodo[1]} · "
                f"{', '.join(series_rotulos[s] for s in series_sel)}"
            ),
            limite=30,
        )
        svg_bloco(svg, 78 + 36 + 26 * min(30, len(ranking)))
        st.info("Selecione um ou mais clubes na barra lateral para ver a trajetória ano a ano.")

with aba_ranking:
    limite = st.slider("Quantos clubes exibir", 5, 50, 25, step=5)
    svg = charts.grafico_ranking(
        ranking,
        titulo="Ranking histórico por índice de desempenho",
        subtitulo=(
            f"{periodo[0]}–{periodo[1]} · "
            f"{', '.join(series_rotulos[s] for s in series_sel)}"
        ),
        limite=limite,
    )
    svg_bloco(svg, 78 + 36 + 26 * min(limite, len(ranking)))

    st.subheader("Tabela do ranking")
    st.dataframe(
        ranking.rename(
            columns={
                "clube": "Clube",
                "uf": "UF",
                "indice": "Índice",
                "participacoes": "Temporadas",
                "titulos": "Títulos",
                "melhor": "Melhor posição",
                "primeira": "Primeira",
                "ultima": "Última",
                "A": "Série A",
                "B": "Série B",
                "C": "Série C",
                "D": "Série D",
            }
        )[
            [
                "Clube",
                "UF",
                "Índice",
                "Temporadas",
                "Títulos",
                "Melhor posição",
                "Primeira",
                "Última",
                "Série A",
                "Série B",
                "Série C",
                "Série D",
            ]
        ],
        width="stretch",
        height=460,
        hide_index=True,
    )
    st.caption(
        "O índice é a soma do desempenho de todas as campanhas do clube no recorte — "
        "mudar o período ou os pesos altera o ranking."
    )

with aba_dados:
    st.markdown("**Classificações carregadas**")
    coluna1, coluna2, coluna3 = st.columns(3)
    busca = coluna1.text_input("Buscar clube", "")
    estados = sorted({uf for uf in filtro_base["uf"].dropna().unique()})
    ufs_sel = coluna2.multiselect("Estados", estados)
    series_tabela = coluna3.multiselect(
        "Divisões na tabela", list(scraper.SERIES), default=list(series_sel),
        format_func=lambda s: series_rotulos[s],
    )

    visao = filtro_base[filtro_base["serie"].isin(series_tabela)]
    if busca:
        visao = visao[visao["clube"].str.contains(busca, case=False, na=False)]
    if ufs_sel:
        visao = visao[visao["uf"].isin(ufs_sel)]

    st.dataframe(
        visao.sort_values(["ano", "serie", "posicao"]).rename(
            columns={
                "ano": "Ano",
                "serie": "Série",
                "posicao": "Posição",
                "clube": "Clube",
                "uf": "UF",
                "n_clubes": "Clubes na edição",
                "indice_temporada": "Índice da campanha",
                "pontos": "Pontos",
                "jogos": "Jogos",
                "vitorias": "Vitórias",
                "empates": "Empates",
                "derrotas": "Derrotas",
                "gp": "Gols pró",
                "gc": "Gols contra",
                "sg": "Saldo de gols",
            }
        )[
            ["Ano", "Série", "Posição", "Clube", "UF", "Clubes na edição",
             "Índice da campanha", "Pontos", "Jogos", "Vitórias", "Empates",
             "Derrotas", "Gols pró", "Gols contra", "Saldo de gols"]
        ],
        width="stretch",
        height=620,
        hide_index=True,
    )
    st.caption(
        f"{len(visao)} registros · a coluna *Clubes na edição* mostra quantos clubes "
        "disputaram aquela série no ano (a Série D chegou a ter 68)."
    )

st.divider()
st.caption(
    "Dados: Bola na Área (bolanaarea.com), classificações finais de cada edição. "
    "Clubes identificados por nome + estado, pois vários homônimos existem em UFs diferentes."
)
