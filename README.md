# ⚽ Ranking de Clubes — Brasileirão (Séries A, B, C e D)

Aplicação **Streamlit** que reproduz, para os clubes brasileiros, o gráfico de
desempenho do arquivo `ManchesterCityFC_League_Performance.svg`: faixas
horizontais por divisão e a trajetória do clube (posição final por temporada),
com as cores indicando em qual série ele jogou em cada ano.

Os dados são raspados das classificações finais publicadas no portal
[Bola na Área](https://www.bolanaarea.com):

| Série | Página índice | Edições usadas |
|-------|---------------|----------------|
| A | `gal_brasileirao.htm` | 2001 → 2024 |
| B | `gal_brasileirao_serie_b.htm` | 2001 → 2024 |
| C | `gal_brasileirao_serie_c.htm` | 2001 → 2024 |
| D | `gal_brasileirao_serie_d.htm` | 2009 → 2024 |

Cada linha do conjunto consolidado traz ano, série, posição, clube, estado e as
estatísticas da campanha (pontos, jogos, V/E/D, gols pró/contra, saldo).
Resultado atual: **2.741 registros de 456 clubes**.

> Edições em andamento são descartadas automaticamente: enquanto o site não
> publicou os resultados, ele lista só os participantes (ordem alfabética, tudo
> zerado) e essa tabela é ignorada.

## Como executar

```bash
# 1) dependências (uma vez)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2) aplicação
streamlit run app.py
```

Se o sistema não tiver `venv`/`pip` (Debian/Ubuntu sem `python3-venv`), há duas
saídas:

```bash
sudo apt install python3-venv python3-pip      # opção 1, recomendada
```

```bash
# opção 2: instala no espaço do usuário, sem sudo
curl -sSL https://bootstrap.pypa.io/get-pip.py -o get-pip.py
python3 get-pip.py --user --break-system-packages
python3 -m pip install --user --break-system-packages -r requirements.txt
python3 -m streamlit run app.py
```

Na primeira execução a aplicação baixa as ~90 páginas do site (leva cerca de um
minuto) e grava o resultado em `data/brasileirao.csv`. Depois disso, roda
totalmente offline. Use **🔄 Atualizar dados do site** para incluir novas
edições e **⬇️ Rebaixar tudo novamente** para refazer o download completo.

Para gerar apenas o CSV, sem abrir a interface:

```bash
python scripts/build_dataset.py --forcar --ate 2024
```

Não é necessário instalar nada para essa etapa: o raspador usa apenas a
biblioteca padrão do Python (o `pandas` só entra na consolidação do CSV e na
aplicação).

## Testes

```bash
python tests/test_smoke.py     # offline; usa o CSV local quando ele existe
```

Cobrem o parser (inclusive o formato antigo, com posição e clube em células
separadas, e as edições ainda sem nomes), a separação nome/UF, a inferência de
estado pelo nome do arquivo do escudo, o índice de desempenho e a geração de SVG
para **todos** os clubes do CSV nas duas escalas e nos dois modos de coloração.

## Estrutura

```
app.py                     # interface Streamlit
src/scraper.py             # download + parsing das tabelas (stdlib)
src/clubs.py               # identidade dos clubes (nome + UF, aliases)
src/dataset.py             # DataFrame consolidado e índice de desempenho
src/charts.py              # geração dos SVGs no estilo da referência
scripts/build_dataset.py   # CLI para (re)construir o CSV
tests/test_smoke.py        # verificações rápidas, sem rede
data/raw/*.htm             # cache das páginas baixadas
data/brasileirao.csv       # base consolidada
```

## O gráfico

* **Faixas** — cada divisão é uma faixa cinza (Série A no topo, D embaixo), como
  os *tiers* do gráfico de referência.
* **Linha** — uma linha por clube; nas trocas de divisão ela é partida ao meio,
  metade com a cor da série de origem e metade com a da série de destino.
* **Marcadores** — o formato indica a divisão (círculo/A, quadrado/B,
  triângulo/C, losango/D) e a dica de contexto aparece ao passar o mouse.
* **Escala** — *Proporcional à edição* usa o número de clubes daquele ano (a
  Série D já teve 68); *Comparável entre edições* fixa a escala no maior número
  de clubes do período, permitindo comparar anos diferentes.
* **Interrupções** — quando o clube não disputou a divisão no ano seguinte, a
  linha é cortada (rebaixamento para uma série não exibida, por exemplo).
* **Cor** — por *Divisão* (padrão, melhor para um clube só) ou por *Clube*
  (para comparar vários times; os marcadores continuam indicando a divisão).

Sem clube selecionado, a aba 📈 mostra o gráfico de barras do índice de
desempenho; com um clube, mostra também o resumo das campanhas por série.

## Índice de desempenho

Para cada campanha:

$$\text{índice} = \text{peso}_{\text{série}} \times \frac{n_{\text{clubes}} - \text{posição} + 1}{n_{\text{clubes}}} \times 100$$

Os pesos padrão são A = 4, B = 3, C = 2 e D = 1, ajustáveis na barra lateral. O
índice de um clube é a soma das campanhas carregadas no recorte escolhido —
logo, o recorte de período influencia diretamente o ranking.

## Identidade dos clubes

O site varia a grafia dos nomes entre edições e existem muitos homônimos
(Atlético de MG, PR, GO…). Por isso a chave do clube é **nome normalizado + UF**,
e a UF é deduzida em camadas, da mais segura para a menos:

1. o estado que a própria linha informa (`Atlético (PR)`, `Botafogo-PB`);
2. o nome do arquivo do escudo (`cb_vitoria-es-2.gif` → ES), quando o texto não
   traz o estado;
3. a única UF conhecida para aquele nome em todo o conjunto;
4. a única UF daquele nome na mesma divisão, ou a de uma temporada vizinha.

Quando nada resolve (por exemplo `Vitória` na Série C de 2022), o clube fica
marcado como `??` em vez de ser somado ao clube errado. Nesses casos há três
mapas em `src/clubs.py`:

* `ALIASES` — unifica grafias do mesmo clube. A chave é o nome normalizado e o
  valor é o nome canônico, que pode trazer a UF forçada: `"NOME ANTIGO":
  "Nome Novo|SP"`.
* `ROTULOS` — nome exibido quando ele depende do estado (a mesma chave
  normalizada reúne homônimos). É o caso do **Athletico Paranaense**: a fonte
  escreve `Atlético (PR)` até 2018 e `Athletico (PR)` depois, então
  `("ATLETICO", "PR"): "Athletico Paranaense"` mostra o nome atual sem afetar os
  outros Atléticos (MG, GO, BA, PE, PB, SC).
* `CORRECOES` — força a UF por contexto, com a chave `(série, nome)`:
  `("C", "VITORIA"): "BA"`.

Os nomes exibidos recebem caixa de título, preservando siglas (`CSA`, `CRAC`),
numerais romanos (`XV de Piracicaba`) e partículas (`4 de Julho`).

## Observações sobre a fonte

* As páginas são gravadas em `data/raw` em `windows-1252` → UTF-8, uma por
  edição, e podem ser reprocessadas offline.
* O site tem pequenas inconsistências (por exemplo, a Série C de 2006 não
  atribui a 45ª colocação). O código preserva a posição publicada.
* A raspagem é sequencial, com pausa de 0,3 s entre requisições, para não
  sobrecarregar o servidor.
