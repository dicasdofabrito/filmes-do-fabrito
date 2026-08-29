# Filmes do Fabrito

Catálogo e motor de recomendação pessoal de filmes. Um pipeline em Python
sincroniza diariamente com o TMDB, aplica regras de admissão e pontua cada
filme pela afinidade com o gosto do autor (avaliações e watchlist em
`data/profile.json`). O resultado alimenta um site estático (fileiras na
home, grade filtrável, ficha do filme) publicado no GitHub Pages.

Não há multiusuário: é uma ferramenta de uso pessoal, para um único perfil.

## Configurando o `TMDB_TOKEN`

O pipeline fala com a API do TMDB usando um token de leitura v4, lido do
ambiente — nunca de um arquivo do repositório.

No Windows (PowerShell ou `cmd`), defina a variável de ambiente do usuário e
reabra o terminal para que ela entre em vigor:

```
setx TMDB_TOKEN "seu-token-aqui"
```

**Nunca faça commit do token.** Este repositório é público — um token
commitado fica exposto no histórico do git para sempre, mesmo que a linha
seja removida depois. Se o token vazar, revogue-o e gere outro no painel do
TMDB.

## Rodando o pipeline

Carga inicial (uma vez, para popular `data/catalog.jsonl` do zero varrendo o
`/discover` do TMDB inteiro):

```
python -m sync --carga-inicial
```

Isso leva de **15 a 40 minutos** — é uma varredura completa do acervo do
TMDB respeitando o limite de taxa da API, não um bug se demorar.

Sincronização diária (usa o export de ids do TMDB para processar só o que
mudou desde ontem):

```
python -m sync
```

Em produção isso roda sozinho via GitHub Actions, uma vez por dia. Rodar à
mão serve para testar mudanças no pipeline localmente.

## Arquivos em `data/`

| Arquivo | Conteúdo |
|---|---|
| `catalog.jsonl` | Estado atual do catálogo, um filme por linha, ordenado por id. Fonte de verdade completa — pôster, sinopse, elenco, diretor. |
| `profile.json` | Avaliações (`gostei` / `não gostei`) e watchlist do autor. Filmes removidos do TMDB continuam aqui como registro histórico. |
| `vibes.json` | Dicionário português → ids de keyword do TMDB, usado pela fileira "Hoje a vibe é" e pela busca por vibe. Gerado por `scripts/gerar_vibes.py` (veja abaixo) — não editar ids à mão sem verificar contra a API. |
| `tmdb_ids_ontem.json.gz` | Último export de ids do TMDB, usado para calcular o diff do dia seguinte. |

`site/data/` (index, fileiras, índice de keywords) é gerado pelo build a
partir desses arquivos e não é editado à mão. Está listado no
`.gitignore` para que builds locais não entrem no controle de versão por
engano; quem toca esse caminho no histórico do git é só a sincronização
diária (`.github/workflows/sync.yml`), que força a inclusão com
`git add -f` depois de rodar o build.

### Regerando `data/vibes.json`

`scripts/gerar_vibes.py` é uma ferramenta avulsa de desenvolvimento (não faz
parte do pipeline nem dos testes) que verifica cada expressão em português
contra a API de busca de keywords do TMDB, aceitando um id só quando o nome
da keyword bate exatamente com o termo buscado. Rodar de novo depois de
editar a lista de candidatos dentro do script:

```
python scripts/gerar_vibes.py
```

Requer `TMDB_TOKEN` no ambiente. É a única parte do repositório, fora dos
testes, que fala com a API ao vivo.

## Rodando os testes

```
.venv/Scripts/pytest
```

Os testes não tocam a API do TMDB — as respostas ficam gravadas como
fixtures. O foco é o motor de pontuação, onde um erro é invisível (um
ranking ruim não quebra nada, só decepciona).

## Sobre `limite_index_mb`

O valor de `limite_index_mb` em `config.json` (orçamento de tamanho do
`site/data/index.json`, testado em CI) é **provisório**. Foi estimado antes
de existir um `index.json` real; depois da primeira carga inicial, meça o
tamanho do arquivo gerado e recalibre esse limite para um valor que reflita
o catálogo real com folga de crescimento — não o número inicial do
`config.json`.

## Atribuição

Este produto usa a API do TMDB, mas não é endossado nem certificado pelo
TMDB.
