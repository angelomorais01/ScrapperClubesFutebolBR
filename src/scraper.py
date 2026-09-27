"""Coleta e parsing das classificações finais do Campeonato Brasileiro.

Fonte: https://www.bolanaarea.com (Séries A, B, C e D).

O módulo usa apenas a biblioteca padrão do Python (``urllib`` +
``html.parser``), então funciona sem dependências externas. As páginas são
gravadas em disco (``data/raw``) para permitir reprocessamento offline.
"""

from __future__ import annotations

import html
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Iterable, Sequence

BASE_URL = "https://www.bolanaarea.com"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) RankingClubes/1.0"
)
TIMEOUT = 30
ENCODING = "windows-1252"

#: Arquivo de cada edição por série.
PAGINAS: dict[str, str] = {
    "A": "brasileirao_{ano}.htm",
    "B": "serie_b_{ano}.htm",
    "C": "serie_c_{ano}.htm",
    "D": "serie_d_{ano}.htm",
}

#: Primeira edição disponível no site para cada série.
PRIMEIRO_ANO: dict[str, int] = {"A": 2001, "B": 2001, "C": 2001, "D": 2009}

SERIES: tuple[str, ...] = ("A", "B", "C", "D")

Progresso = Callable[[str, int, int], None]


@dataclass
class LinhaTabela:
    """Uma linha de tabela: textos das células e arquivos de imagem citados."""

    celulas: list[str] = field(default_factory=list)
    imagens: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------
@dataclass
class Classificacao:
    """Uma linha da classificação final de uma edição."""

    ano: int
    serie: str
    posicao: int
    clube_bruto: str
    celulas: list[str] = field(default_factory=list)
    imagens: list[str] = field(default_factory=list)

    @property
    def estatisticas(self) -> list[str]:
        """Valores numéricos que seguem o nome do clube (PG, J, V, E, D, GP, GC, SG)."""
        return [c for c in self.celulas if re.fullmatch(r"-?\d+", c)]


# ---------------------------------------------------------------------------
# Parser de tabelas HTML (stdlib)
# ---------------------------------------------------------------------------
POS_ONLY = re.compile(r"^(\d{1,3})\s*[º°o]$", re.IGNORECASE)
POS_NAME = re.compile(r"^(\d{1,3})\s*[º°o]\s*(\S.*)$", re.IGNORECASE | re.DOTALL)
NUM = re.compile(r"^-?\d+$")

_CABECALHO_DICAS = (
    "CLUBE",
    "CLUBES",
    "EQUIPE",
    "TIME",
    "TIMES",
    "PARTICIPANTE",
    "CLASSIFICA",
    "FINALISTA",
)


class _TableParser(HTMLParser):
    """Extrai todas as tabelas do documento como listas de linhas/células.

    Além do texto, cada linha guarda os arquivos de imagem citados (os escudos
    trazem a UF do clube no nome do arquivo, o que ajuda a desambiguar
    homônimos como *Botafogo* ou *Vitória*).
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[LinhaTabela]] = []
        self.stack: list[dict] = []

    # -- tags ---------------------------------------------------------
    def handle_starttag(self, tag, attrs):  # noqa: D102 - ver HTMLParser
        tag = tag.lower()
        if tag == "table":
            self.stack.append({"rows": [], "cur": None, "buf": None, "imgs": None})
        elif tag == "tr" and self.stack:
            self.stack[-1]["cur"] = LinhaTabela()
            self.stack[-1]["imgs"] = self.stack[-1]["cur"].imagens
        elif tag in ("td", "th") and self.stack:
            self.stack[-1]["buf"] = []
        elif tag == "img" and self.stack:
            self._registrar_imagem(attrs)
            if self.stack[-1]["buf"] is not None:
                self.stack[-1]["buf"].append(" ")
        elif (
            tag in ("br", "p")
            and self.stack
            and self.stack[-1]["buf"] is not None
        ):
            self.stack[-1]["buf"].append(" ")

    def handle_startendtag(self, tag, attrs):
        tag = tag.lower()
        if tag == "img" and self.stack:
            self._registrar_imagem(attrs)
            if self.stack[-1]["buf"] is not None:
                self.stack[-1]["buf"].append(" ")
        elif tag == "br" and self.stack and self.stack[-1]["buf"] is not None:
            self.stack[-1]["buf"].append(" ")

    def _registrar_imagem(self, attrs) -> None:
        destino = self.stack[-1].get("imgs")
        if destino is None:
            return
        for chave, valor in attrs:
            if chave.lower() == "src" and valor:
                destino.append(str(valor))
                break

    def handle_data(self, data):
        if self.stack and self.stack[-1]["buf"] is not None:
            self.stack[-1]["buf"].append(data)

    def handle_endtag(self, tag):  # noqa: D102
        tag = tag.lower()
        if not self.stack:
            return
        top = self.stack[-1]
        if tag in ("td", "th") and top["buf"] is not None:
            bruto = "".join(top["buf"])
            texto = re.sub(r"\s+", " ", html.unescape(bruto).replace("\xa0", " ")).strip()
            if top["cur"] is not None:
                top["cur"].celulas.append(texto)
            top["buf"] = None
        elif tag == "tr" and top["cur"] is not None:
            if any(c.strip() for c in top["cur"].celulas):
                top["rows"].append(top["cur"])
            top["cur"] = None
            top["imgs"] = None
        elif tag == "table":
            if top["cur"] is not None and any(c.strip() for c in top["cur"].celulas):
                top["rows"].append(top["cur"])
            self.stack.pop()
            if top["rows"]:
                self.tables.append(top["rows"])


def parse_tabelas(documento: str) -> list[list[LinhaTabela]]:
    """Devolve todas as tabelas de um documento HTML."""
    parser = _TableParser()
    parser.feed(documento)
    parser.close()
    return parser.tables


# ---------------------------------------------------------------------------
# Extração da classificação
# ---------------------------------------------------------------------------
#: Um nome de clube precisa de pelo menos esta quantidade de letras. Isso
#: descarta tabelas de edições ainda não preenchidas, em que o site publica
#: ``.`` no escudo e ``..`` no lugar do nome.
_MIN_LETRAS = 3


def _tem_nome(texto: str) -> bool:
    return sum(1 for c in texto if c.isalpha()) >= _MIN_LETRAS


def _posicao_da_linha(linha: LinhaTabela) -> tuple[int, str, int] | None:
    """Localiza posição/clube numa linha. Devolve (posição, clube, índice da célula)."""
    celulas = linha.celulas
    for idx, celula in enumerate(celulas):
        m = POS_ONLY.match(celula)
        if m:
            for desloc, seguinte in enumerate(celulas[idx + 1: idx + 4], start=1):
                if _tem_nome(seguinte):
                    return int(m.group(1)), seguinte.strip(), idx + desloc
            return None
        m = POS_NAME.match(celula)
        if m and idx <= 2 and _tem_nome(m.group(2)):
            return int(m.group(1)), m.group(2).strip(), idx
    return None


def _parece_dados(linha: LinhaTabela) -> bool:
    return sum(1 for c in linha.celulas if NUM.match(c)) >= 3


def extrair_linhas(tabela: list[LinhaTabela]) -> list[Classificacao]:
    """Converte uma tabela HTML em linhas de classificação (ordenadas por posição)."""
    cabecalho = None
    for i, linha in enumerate(tabela[:8]):
        texto = " ".join(linha.celulas)
        if len(linha.celulas) >= 3 and any(d in texto.upper() for d in _CABECALHO_DICAS):
            cabecalho = i
            break
    inicio = 0 if cabecalho is None else cabecalho + 1

    achados: list[tuple[int, str, list[str], list[str]]] = []
    for linha in tabela[inicio:]:
        if len(linha.celulas) < 3 or not _parece_dados(linha):
            continue
        achado = _posicao_da_linha(linha)
        if achado:
            posicao, clube, idx = achado
            achados.append((posicao, clube, linha.celulas[idx + 1:], linha.imagens))
    achados.sort(key=lambda item: item[0])
    return [
        Classificacao(
            ano=0,
            serie="",
            posicao=p,
            clube_bruto=c,
            celulas=cels,
            imagens=imgs,
        )
        for p, c, cels, imgs in achados
    ]


def _pontuar(linhas: Sequence[Classificacao]) -> tuple[bool, int] | None:
    posicoes = [linha.posicao for linha in linhas]
    if len(posicoes) < 8 or len(set(posicoes)) != len(posicoes):
        return None
    sequencial = posicoes == list(range(1, len(posicoes) + 1))
    return sequencial, len(linhas)


def extrair_classificacao(documento: str) -> list[Classificacao]:
    """Escolhe a tabela de classificação final mais completa do documento."""
    melhor: list[Classificacao] = []
    melhor_score: tuple[bool, int] | None = None
    for tabela in parse_tabelas(documento):
        linhas = extrair_linhas(tabela)
        score = _pontuar(linhas)
        if score and (melhor_score is None or score > melhor_score):
            melhor, melhor_score = linhas, score
    return melhor


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------
def url_edicao(ano: int, serie: str) -> str:
    """URL da página de uma edição."""
    return f"{BASE_URL}/{PAGINAS[serie].format(ano=ano)}"


def baixar(url: str, tentativas: int = 3, espera: float = 1.5) -> str:
    """Baixa uma página e devolve o texto decodificado (windows-1252)."""
    ultimo_erro: Exception | None = None
    for tentativa in range(1, tentativas + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resposta:
                return resposta.read().decode(ENCODING, "replace")
        except (urllib.error.URLError, TimeoutError, OSError) as erro:  # pragma: no cover
            ultimo_erro = erro
            if tentativa < tentativas:
                time.sleep(espera * tentativa)
    raise RuntimeError(f"Falha ao baixar {url}: {ultimo_erro}")


def anos_disponiveis(serie: str, ate: int | None = None) -> list[int]:
    """Anos com edição disponível para a série."""
    if ate is None:
        ate = time.localtime().tm_year
    return list(range(PRIMEIRO_ANO[serie], ate + 1))


def coletar(
    pasta_raw: Path,
    series: Iterable[str] = SERIES,
    ate: int | None = None,
    intervalo: float = 0.3,
    forcar: bool = False,
    progresso: Progresso | None = None,
) -> list[Classificacao]:
    """Baixa (ou reaproveita o cache local) e devolve as classificações finais.

    Args:
        pasta_raw: diretório onde as páginas HTML são armazenadas.
        series: séries a coletar (``"A"``, ``"B"``, ``"C"``, ``"D"``).
        ate: último ano a considerar (inclusive).
        intervalo: pausa entre requisições, em segundos.
        forcar: se ``True``, ignora o cache e baixa novamente.
        progresso: callback ``(mensagem, atual, total)`` para barras de progresso.
    """
    pasta_raw.mkdir(parents=True, exist_ok=True)
    trabalhos: list[tuple[int, str]] = []
    for serie in series:
        for ano in anos_disponiveis(serie, ate):
            trabalhos.append((ano, serie))

    registros: list[Classificacao] = []
    total = len(trabalhos)
    for i, (ano, serie) in enumerate(trabalhos, start=1):
        if progresso:
            progresso(f"{serie} · {ano}", i, total)
        destino = pasta_raw / f"{serie}_{ano}.htm"
        if forcar or not destino.exists():
            try:
                texto = baixar(url_edicao(ano, serie))
                destino.write_text(texto, encoding="utf-8")
                time.sleep(intervalo)
            except RuntimeError:
                continue
        else:
            texto = destino.read_text(encoding="utf-8")

        try:
            linhas = extrair_classificacao(texto)
        except Exception:  # pragma: no cover - documento inesperado
            linhas = []
        for linha in linhas:
            linha.ano = ano
            linha.serie = serie
            registros.append(linha)
    return registros
