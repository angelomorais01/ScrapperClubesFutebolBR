"""Coleta, consolidação e visualização das classificações do Campeonato
Brasileiro (Séries A, B, C e D).

Os submódulos **não** são importados automaticamente: ``scraper`` e ``clubs``
funcionam apenas com a biblioteca padrão, enquanto ``dataset`` e ``charts``
exigem ``pandas``. Importe o que precisar::

    from src import scraper
    from src import dataset  # requer pandas
"""

__all__ = ["charts", "clubs", "dataset", "scraper"]
