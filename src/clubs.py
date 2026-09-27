"""Unificação de nomes de clubes entre edições.

As tabelas do bolanaarea.com variam a grafia ao longo dos anos
(``Atlético (PR)`` / ``ATHLETICO (PR)``, ``Sport (PE)`` / ``Sport Recife (PE)``
etc.). Como vários clubes compartilham o mesmo nome em estados diferentes
(Atlético de MG, PR, GO, PB...), a identidade de um clube é o par
**nome + UF**.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Iterable, Sequence

#: Unidades federativas brasileiras reconhecidas nas tabelas.
UFS: frozenset[str] = frozenset(
    """AC AL AM AP BA CE DF ES GO MA MG MS MT PA PB PE PI PR RJ RN RO RR RS SC SE SP TO""".split()
)

#: Artefatos usados pelo site para marcar observações no nome.
_ARTEFATOS = re.compile(r"[\s*×•·.]+$")
_PAREN = re.compile(r"^(?P<nome>.*?)\s*\((?P<uf>[A-Za-z]{2})\)$")
_SEP = re.compile(r"^(?P<nome>.*?)\s*[-–—/]\s*(?P<uf>[A-Za-z]{2})$")
_SUFIXO = re.compile(r"^(?P<nome>.*?)\s+(?P<uf>[A-Za-z]{2})$")
_SIGLA_ESCUDO = re.compile(r"[-_]([a-z]{2})(?=[-_.]|$)")
_ROMANO = re.compile(r"^[IVX]{1,4}$", re.IGNORECASE)

#: Clubes que mudaram de nome/grafia e devem ser tratados como um só.
#:
#: A **chave** é o nome normalizado (sem acentos, maiúsculas) usado na busca; o
#: **valor** é o nome canônico já pronto para exibição e pode trazer a UF
#: forçada na forma ``Nome|UF``.
ALIASES: dict[str, str] = {
    "ATHLETICO": "Atlético",                        # Athletico Paranaense (PR)
    "ATHLETICO PARANAENSE": "Atlético",             # idem, nome completo atual
    "GREMIO BARUERI": "Barueri",                    # Grêmio Barueri (SP)
    "INTER DE LAJES": "Inter de Lages",
    "SPORT RECIFE": "Sport",
    "XV PIRACICABA": "XV de Piracicaba",
    "AGUIA MARABA": "Águia de Marabá",
    "ATL SOROCABA": "Atlético Sorocaba",            # abreviação do site
    "VIT CONQUISTA": "Vitória da Conquista",        # abreviação do site
    "RIO BRANCOVT": "Rio Branco|ES",                # Rio Branco-VT (ES)
    "RIO BRANCOVN": "Rio Branco|ES",                # Rio Branco-VN (ES)
}

#: Nome exibido quando a grafia depende do estado — necessário para homônimos,
#: já que a mesma chave normalizada reúne clubes de UFs diferentes.
#: Chave: ``(nome normalizado, UF)``.
ROTULOS: dict[tuple[str, str], str] = {
    # O Athletico Paranaense mudou de nome em 2019 e a fonte ora escreve
    # "Atlético (PR)", ora "Athletico (PR)". O rótulo usa o nome atual; a UF é
    # obrigatória porque "Atlético" também existe em MG, GO, BA, PE, PB e SC.
    ("ATLETICO", "PR"): "Athletico Paranaense",
}

_MINUSCULAS = {"de", "da", "do", "das", "dos", "e", "del"}

#: Nomes que são siglas e devem continuar em caixa alta na interface.
ACRONIMOS: frozenset[str] = frozenset(
    {
        "ABC", "ADAP", "ADESG", "ASA", "CENE", "CFA", "CFZ", "CRAC", "CRB",
        "CSA", "CSE", "GAS", "ICASA", "PSTC", "URT",
    }
)

#: UF forçada por contexto, quando o nome do clube tem homônimos e o próprio
#: site omite o estado. Chave: ``(série, nome normalizado)``.
CORRECOES: dict[tuple[str, str], str] = {
    # Série C 2022: a página escreve só "VITÓRIA". É o Vitória (BA), rebaixado
    # em 2021 (não há linha dele na Série B de 2022) e 4º colocado na Série C.
    ("C", "VITORIA"): "BA",
}


def sem_acento(texto: str) -> str:
    """Remove acentuação, preservando as letras."""
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c))


def normalizar(nome: str) -> str:
    """Forma canônica de um nome de clube (sem acento, maiúsculo, sem ruído)."""
    return _chave(nome_canonico(nome))


def nome_canonico(nome: str) -> str:
    """Nome de exibição já unificado pelos :data:`ALIASES`."""
    destino = ALIASES.get(_chave(nome))
    return destino.split("|")[0] if destino else nome


def uf_forcada(nome: str) -> str | None:
    """UF definida explicitamente no mapa de aliases, se houver."""
    destino = ALIASES.get(_chave(nome), "")
    return destino.split("|", 1)[1] if "|" in destino else None


def _chave(nome: str) -> str:
    """Normaliza para comparação (sem acentos, maiúsculo, só letras/números)."""
    limpo = sem_acento(nome).upper()
    limpo = re.sub(r"[^A-Z0-9 ]+", " ", limpo)
    return re.sub(r"\s+", " ", limpo).strip()


def separar_uf(clube_bruto: str) -> tuple[str, str | None]:
    """Separa o nome do clube da UF, quando presente.

    >>> separar_uf("Atlético (PR)")
    ('Atlético', 'PR')
    >>> separar_uf("Botafogo-PB")
    ('Botafogo', 'PB')
    >>> separar_uf("Mirassol")
    ('Mirassol', None)
    """
    texto = _ARTEFATOS.sub("", clube_bruto.replace("\xa0", " ")).strip()
    texto = re.sub(r"\s+", " ", texto)
    for padrao in (_PAREN, _SEP, _SUFIXO):
        m = padrao.match(texto)
        if m and m.group("uf").upper() in UFS:
            return m.group("nome").strip(), m.group("uf").upper()
    return texto, None


def uf_do_escudo(imagens: Iterable[str]) -> str | None:
    """Deduz a UF pelo nome dos arquivos de escudo (``cb_vitoria-es-2.gif``).

    Vários homônimos aparecem sem o estado no texto, mas o arquivo do escudo
    carrega a sigla. Só devolve algo quando todos os escudos concordam.
    """
    encontradas = set()
    for arquivo in imagens:
        nome = Path(str(arquivo)).name.lower()
        if not nome.startswith("cb_"):
            continue
        for sigla in _SIGLA_ESCUDO.findall(nome):
            if sigla.upper() in UFS:
                encontradas.add(sigla.upper())
    if len(encontradas) == 1:
        return next(iter(encontradas))
    return None


def formatar_nome(nome: str) -> str:
    """Apresentação legível do nome (``VILA NOVA`` -> ``Vila Nova``).

    Siglas conhecidas (:data:`ACRONIMOS`), numerais romanos (``XV``) e as
    partículas (``de``, ``da``, ``do``...) seguem regras próprias.
    """
    partes = [
        palavra.upper()
        if palavra.upper() in ACRONIMOS or _ROMANO.match(palavra)
        else palavra.title()
        for palavra in nome.split()
    ]
    return " ".join(
        palavra.lower() if i and palavra.lower() in _MINUSCULAS else palavra
        for i, palavra in enumerate(partes)
    )


class CatalogoClubes:
    """Consolida a identidade dos clubes (nome + UF) a partir das classificações.

    A UF é deduzida em três níveis, do mais seguro para o menos:

    1. a UF que a própria linha informa;
    2. a única UF conhecida para aquele nome em todo o conjunto;
    3. a única UF daquele nome **na mesma divisão**;
    4. a UF usada por aquele nome, na mesma divisão, numa temporada vizinha.

    Quando nada disso resolve (``Botafogo``, ``Vitória``, ``São José``... podem
    ser de vários estados), o clube fica identificado como ``??`` em vez de ser
    somado ao clube errado. Use :data:`ALIASES` ou :data:`CORRECOES` para
    apontar o destino correto.
    """

    def __init__(self, registros: Iterable[tuple[int, str, str, Sequence[str]]]) -> None:
        """Recebe ``(ano, série, nome bruto, arquivos de escudo)`` de cada linha."""
        global_uf: dict[str, Counter] = {}
        serie_uf: dict[tuple[str, str], Counter] = {}
        por_ano: dict[tuple[str, str], dict[int, str]] = {}
        descartados: set[str] = set()
        for ano, serie, bruto, imagens in registros:
            nome, uf = separar_uf(bruto)
            chave = normalizar(nome)
            if not chave:
                continue
            if uf is None:
                uf = uf_do_escudo(imagens) or uf_forcada(nome)
            if uf:
                global_uf.setdefault(chave, Counter())[uf] += 1
                serie_uf.setdefault((serie, chave), Counter())[uf] += 1
                por_ano.setdefault((serie, chave), {})[ano] = uf
            else:
                descartados.add(chave)
        self._global = global_uf
        self._serie = serie_uf
        self._por_ano = por_ano
        self._pendentes = descartados

    def _inferir_uf(self, chave: str, serie: str | None, ano: int | None) -> str | None:
        candidatos = self._global.get(chave)
        if not candidatos:
            return None
        if len(candidatos) == 1:
            return next(iter(candidatos))

        forcada = CORRECOES.get((serie, chave))
        if forcada:
            return forcada

        if serie is not None:
            na_serie = self._serie.get((serie, chave))
            if na_serie and len(na_serie) == 1:
                return next(iter(na_serie))
            if na_serie and ano is not None:
                historico = self._por_ano.get((serie, chave), {})
                vizinhos = [uf for a, uf in historico.items() if abs(a - ano) == 1]
                if len(set(vizinhos)) == 1:
                    return vizinhos[0]
        return None

    def identificar(
        self,
        clube_bruto: str,
        serie: str | None = None,
        ano: int | None = None,
        imagens: Sequence[str] = (),
    ) -> tuple[str, str | None, str]:
        """Devolve ``(id, uf, nome_exibido)`` para o nome bruto da tabela."""
        nome, uf = separar_uf(clube_bruto)
        chave = normalizar(nome)
        if uf is None:
            uf = (
                uf_do_escudo(imagens)
                or uf_forcada(nome)
                or self._inferir_uf(chave, serie, ano)
            )
        exibicao = ROTULOS.get((chave, uf or "")) or formatar_nome(nome_canonico(nome))
        if uf:
            exibicao = f"{exibicao} ({uf})"
        return f"{chave}|{uf or '??'}", uf, exibicao

    def nao_resolvidos(self) -> list[str]:
        """Nomes sem UF que têm mais de um candidato (para ampliar :data:`CORRECOES`)."""
        return sorted(chave for chave in self._pendentes if len(self._global.get(chave, {})) != 1)
