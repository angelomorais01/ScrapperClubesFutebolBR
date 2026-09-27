#!/usr/bin/env python3
"""Constrói ``data/brasileirao.csv`` a partir das páginas do Bola na Área.

Exemplos::

    python scripts/build_dataset.py                      # usa o cache local
    python scripts/build_dataset.py --forcar             # baixa tudo de novo
    python scripts/build_dataset.py --series A B         # só duas divisões
    python scripts/build_dataset.py --ate 2010           # recorte histórico
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from src import dataset, scraper  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--series", nargs="+", default=list(scraper.SERIES),
                        choices=list(scraper.SERIES), help="divisões a coletar")
    parser.add_argument("--ate", type=int, default=None, help="último ano (inclusive)")
    parser.add_argument("--forcar", action="store_true", help="refaz o download de tudo")
    parser.add_argument("--intervalo", type=float, default=0.3,
                        help="pausa entre requisições, em segundos")
    parser.add_argument("--saida", type=Path, default=RAIZ / "data" / "brasileirao.csv")
    parser.add_argument("--bruto", type=Path, default=RAIZ / "data" / "raw")
    args = parser.parse_args()

    def progresso(mensagem: str, atual: int, total: int) -> None:
        print(f"\r[{atual:3d}/{total}] {mensagem:20s}", end="", flush=True)

    df = dataset.atualizar(
        args.saida,
        args.bruto,
        series=args.series,
        ate=args.ate,
        forcar=args.forcar,
        intervalo=args.intervalo,
        progresso=progresso,
    )
    print()
    if df.empty:
        print("Nenhum registro coletado.")
        return 1

    ignoradas = df.attrs.get("edicoes_ignoradas") or []
    if ignoradas:
        lista = ", ".join(f"{serie} {ano}" for ano, serie in ignoradas)
        print(f"Edições sem resultados publicados (ignoradas): {lista}")

    print(f"{len(df)} registros de {df['clube'].nunique()} clubes gravados em {args.saida}")
    print(df.groupby(["serie"])["ano"].agg(["min", "max", "nunique"]).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
