# Filmes do Fabrito — catálogo e motor de recomendação pessoal de filmes

**Data:** 27 de agosto de 2026
**Autor:** Fabio (design conduzido em sessão de brainstorming)
**Status:** aprovado, pronto para plano de implementação

Nome do produto: **Filmes do Fabrito**. Repositório e diretório:
`filmes-do-fabrito`.

---

## 1. Objetivo

Ferramenta pessoal, de uso exclusivo do autor, que responde três perguntas:

1. **O que eu assisto hoje?** — recomendação rankeada pelo gosto pessoal.
2. **Gostei de X, o que mais eu gostaria?** — vizinhança de um filme específico.
3. **Quero algo com a vibe Y que eu ainda não vi** — busca por tema em
   linguagem natural.

O sistema aprende com marcações de *já vi*, *gostei* e *não gostei*.

**Não é** um produto, não tem outros usuários, não tem SEO, não tem contas.

## 2. Premissas de escopo

| Premissa | Decisão |
|---|---|
| Mídia | Somente filmes. Séries fora. |
| Disponibilidade | O autor tem acesso a todos os filmes já lançados. Streaming não é modelado. |
| Única exceção | Filmes em cartaz no cinema e ainda sem lançamento doméstico — separados em área própria. |
| Filtros de conteúdo | Nenhum por idioma, país, época ou tipo. Animação, documentário, mudo e estrangeiro são elegíveis. |
| Idioma da interface | Português do Brasil. |

## 3. Arquitetura

Três peças, um único repositório público no GitHub. Sem servidor, sem banco
hospedado, sem custo recorrente.

```
GitHub Actions (cron diário)  →  pipeline Python  →  commit no repositório
                                                          ↓
                                              GitHub Pages serve o site
                                                          ↓
                                    navegador escreve o perfil de volta via API
```

O GitHub acumula quatro papéis: agendador, banco de dados, versionamento e
hospedagem.

**O repositório é público** porque o GitHub Pages gratuito só publica a partir
de repositórios públicos. O perfil de avaliações fica visível — aceito
explicitamente pelo autor.

### Estrutura de arquivos

```
filmes-do-fabrito/
├─ .github/workflows/sync.yml      # cron diário 09:00 UTC (06:00 BRT)
├─ sync/
│  ├─ fetch.py                     # cliente TMDB: export de ids, discover, detalhes
│  ├─ catalog.py                   # regras de admissão e manutenção do catálogo
│  ├─ theatrical.py                # classificação "nos cinemas" vs "disponível"
│  ├─ profile.py                   # leitura do perfil, construção do vetor de gosto
│  ├─ score.py                     # motor de pontuação
│  ├─ shelves.py                   # geração das fileiras da home
│  └─ build.py                     # escrita dos artefatos do site
├─ data/
│  ├─ catalog.jsonl                # estado atual, 1 filme por linha, ordenado por id
│  ├─ profile.json                 # avaliações e watchlist do autor
│  ├─ vibes.json                   # dicionário português → keywords do TMDB
│  └─ tmdb_ids_ontem.json.gz       # último export de ids, para o diff
├─ site/
│  ├─ index.html
│  ├─ app.js  ·  ui.js  ·  store.js  ·  github.js
│  ├─ style.css
│  └─ data/                        # gerado pelo build, não editado à mão
│     ├─ index.json                # catálogo enxuto + score por filme
│     ├─ shelves.json              # as fileiras já montadas
│     └─ keywords.json             # índice invertido para busca por vibe
├─ tests/
├─ config.json
└─ README.md
```

## 4. Modelo de dados

### 4.1 `data/catalog.jsonl`

Um filme por linha, ordenado por `id`. Chaves abreviadas para reduzir tamanho.
A ordenação estável é o que permite ao git guardar apenas o delta diário — um
snapshot completo por dia custaria centenas de MB por ano.

```json
{"id":603,"t":"Matrix","y":1999,"r":136,"g":[28,878],
 "k":[1701,9743,4458],"v":8.2,"n":25431,
 "d":[9339],"c":[6384,2975,10990],"l":"en","st":"acervo","th":false}
```

| Campo | Significado |
|---|---|
| `id` | id do TMDB |
| `t` / `y` / `r` | título em pt-BR, ano, duração em minutos |
| `g` / `k` | ids de gêneros e de keywords |
| `v` / `n` | nota média e número de votos |
| `d` / `c` | ids de diretores e do elenco principal (até 5) |
| `l` | idioma original |
| `st` | trilha de admissão: `acervo` ou `recente` |
| `th` | `true` se está em cartaz e ainda sem lançamento doméstico |

### 4.2 `data/profile.json`

```json
{
  "updated": "2026-08-27T18:04:00Z",
  "movies": {
    "603":   {"seen": true,  "rating":  1, "at": "2026-08-20"},
    "27205": {"seen": true,  "rating": -1, "at": "2026-08-22"},
    "155":   {"seen": false, "want": true, "at": "2026-08-25"}
  }
}
```

`rating` é ternário: `1` gostei, `-1` não gostei, ausente para neutro.
`want` marca a watchlist. Filmes removidos do TMDB permanecem aqui como
registros órfãos — o histórico do autor nunca é apagado por decisão do
pipeline.

### 4.3 `data/vibes.json`

Dicionário curado que resolve o descompasso de idioma: as keywords do TMDB são
em inglês, as consultas do autor são em português.

```json
{"fim do mundo": [4458, 9951, 1701, 12565],
 "assalto":      [10051, 779],
 "found footage":[15012]}
```

Cerca de 250 expressões na versão inicial. Editável à mão para crescer.

## 5. Pipeline de sync

Roda diariamente às 06:00 BRT.

```
1. baixa o export diário de ids de filmes do TMDB
2. compara com o export de ontem → conjunto de ids novos
3. para cada id novo, busca detalhes e aplica as regras de admissão
4. reavalia a trilha "recente": quem graduou, quem expirou
5. atualiza a classificação "nos cinemas" via release_dates
6. lê profile.json e constrói o vetor de gosto
7. pontua o catálogo inteiro contra o perfil
8. monta as fileiras e escreve site/data/
9. commit e push
```

### 5.1 Regras de admissão

Duas trilhas, porque um corte único não serve aos dois casos: um filme lançado
ontem tem 3 votos e seria excluído por qualquer limiar de consenso.

| | Acervo | Recente |
|---|---|---|
| Critério | `vote_count >= 50` | lançado nos últimos 18 meses |
| Filtro extra | — | `vote_count >= 5` **ou** `popularity >= piso` |
| Comuns a ambas | `adult = false`, `runtime >= 60` | idem |

Um filme entra por *Recente* no dia do lançamento. Se acumular 50 votos dentro
de 18 meses, gradua para *Acervo* permanentemente. Se não, sai do catálogo.

Filmes presentes no `profile.json` entram sempre, independentemente dos cortes.

Volume estimado: ~40 mil filmes.

### 5.2 Classificação "nos cinemas"

Pelo endpoint `release_dates`, não pelo `now_playing`. A regra: **tem
lançamento teatral no Brasil e ainda não tem lançamento digital nem físico**.
Quando o digital sai, o filme migra sozinho para o catálogo principal.

O `now_playing` devolveria uma lista de títulos em cartaz sem informar se já
saíram em casa — insuficiente para a distinção que interessa aqui.

### 5.3 Contorno do teto do `/discover`

O `/discover` para em 500 páginas (10.000 resultados) por consulta. Quando uma
consulta estoura esse limite, o fetch a fatia recursivamente por faixa de ano de
lançamento até cada fatia caber, e concatena os resultados.

Na operação normal o export diário de ids torna isso raro; a rotina existe para
a carga inicial e para o fallback.

## 6. Motor de recomendação

Baseado em conteúdo. Determinístico, offline, sem dependência de IA ou de
serviço externo.

### 6.1 Construção do vetor de gosto

Para cada característica `f` (keyword, diretor, ator, gênero, década, idioma):

```
n_pos(f)  = filmes curtidos que contêm f
n_neg(f)  = filmes rejeitados que contêm f

afinidade(f) = (n_pos − n_neg) / (n_pos + n_neg + k)     com k = 2
idf(f)       = log(N_catálogo / (1 + filmes_com_f))
peso(f)      = afinidade(f) × idf(f)
```

O `k` é suavização bayesiana: impede que uma única observação vire convicção.

**A normalização por raridade (`idf`) é o que faz o motor funcionar.** Sem ela,
`drama` domina — aparece em 40% do acervo e não informa nada sobre o autor. Com
ela, `post-apocalyptic` pesa muito mais, porque é raro e portanto discriminante.

### 6.2 Pontuação de um filme

Pesos por tipo de sinal, aprovados pelo autor:

| Sinal | Peso |
|---|---|
| Keywords | 0,40 |
| Diretor | 0,20 |
| Elenco principal | 0,15 |
| Gêneros | 0,15 |
| Década | 0,06 |
| Idioma original | 0,04 |

```
s_t(filme)  = média de peso(f) das características de tipo t presentes
afinidade   = Σ  W't × s_t(filme)
```

`normalizar(afinidade)` é min–max sobre a distribuição de afinidade do
catálogo inteiro naquele build, resultando em `[0, 1]`.

**Redistribuição de peso por ausência.** Se um filme não tem keywords, `W` das
keywords é redistribuído proporcionalmente entre os sinais presentes, e não
contado como zero. Sem isso o motor penalizaria sistematicamente os filmes de
cobertura fraca no TMDB — justamente os obscuros que o autor quer descobrir.

Âncora de qualidade, para um filme com nota 9,8 e 51 votos não vencer tudo:

```
qualidade = (n/(n+m))·v + (m/(n+m))·C     com m = 500, C = média global

score = 0,75 · normalizar(afinidade) + 0,25 · qualidade
```

### 6.3 Partida a frio

Com menos de 10 avaliações não há sinal utilizável: o score cai para
`qualidade` pura. A primeira abertura do app dispara um onboarding que
apresenta, em sequência rápida para marcação, uma amostra dos 200 filmes de
maior `vote_count` do catálogo, diversificada por década e por gênero para não
oferecer vinte blockbusters americanos seguidos. O motor fica utilizável em
torno de 20 avaliações e bom em torno de 100.

### 6.4 "Gostei de X, o que mais?"

Mesma maquinaria, com o vetor de gosto construído a partir de um único filme.
Disponível como ação em qualquer ficha.

## 7. Interface

Três telas em escada. Sem framework, sem etapa de build.

```
Home (fileiras)  ──clique no título da fileira──▶  Grade filtrada
       │
       └──────────clique num filme─────────────▶  Ficha do filme
```

### 7.1 Home — fileiras

Ordem fixa: contexto imediato, depois gosto, depois serendipidade. As cinco
primeiras renderizam imediatamente; o restante carrega conforme a rolagem.

| # | Fileira | Regra |
|---|---|---|
| 1 | Você marcou pra ver | `want = true` |
| 2 | Entrou hoje no catálogo | admitidos nas últimas 24h, rankeados por score |
| 3 | Porque você gostou de *X* | vizinhança do último filme curtido |
| 4 | Hoje a vibe é: *Y* | vibe sorteada com semente na data, entre as de afinidade positiva |
| 5 | Mais de *[diretor]* | diretor de maior peso no perfil, não vistos |
| 6 | Com *[ator]* | idem, por elenco |
| 7 | Cabe antes de dormir | `runtime < 100`, por score |
| 8 | Clássicos que você nunca viu | lançados há mais de 25 anos, qualidade no top 2%, ausentes do perfil |
| 9 | Aposta arriscada | afinidade no percentil 40–70 **entre os não vistos**, qualidade no top 5% |
| 10 | Ponto cego | a dimensão (gênero, idioma ou década) de menor razão *presença nos curtidos ÷ presença no catálogo*, exigindo ao menos 200 filmes no catálogo para ser elegível; dentro dela, só qualidade no top 2%, não vistos |
| 11 | Nos cinemas | `th = true` |

As fileiras 9 e 10 existem para combater a bolha que o próprio motor cria. Sem
elas o sistema converge para mais do mesmo.

A lista, sua ordem e o liga/desliga de cada fileira vivem em `config.json`.

### 7.2 Grade

O "ver tudo" de qualquer fileira. Pôsteres ordenados por score, com filtros
laterais: gênero, década, vibe, duração, visto/não visto.

### 7.3 Ficha do filme

Pôster, sinopse, ano, duração, diretor, elenco, keywords, e a justificativa da
recomendação em linguagem natural ("porque você gostou de *Stalker* e de outros
três filmes de Tarkovsky"). Ações: **já vi** · **gostei** · **não gostei** ·
**quero ver** · **o que mais se parece com esse**.

### 7.4 Busca por vibe

Campo de texto casado contra `vibes.json`. O índice invertido de keywords
carrega sob demanda, apenas quando a busca é usada.

## 8. Persistência do perfil

O perfil precisa estar no repositório porque o pipeline o lê a cada build. Um
perfil que vivesse só no navegador nunca alimentaria as recomendações.

**Mecanismo:** token do GitHub de escopo restrito (somente este repositório,
somente conteúdo), colado uma vez por aparelho e guardado no `localStorage`. O
site faz o commit direto pela API.

**Lote, não gota a gota.** Avaliações se acumulam localmente e são enviadas em
um único commit após um intervalo de inatividade. Vinte marcações no onboarding
produzem um commit, não vinte.

**Conflito.** A API exige o SHA do arquivo. Em caso de 409 — o autor avaliou no
celular e no computador quase ao mesmo tempo — o site recarrega o perfil, funde
por filme com o registro de `at` mais recente vencendo, e reenvia. Até três
tentativas.

**Token ausente ou revogado.** O site avisa e retém as avaliações localmente
até um token válido ser fornecido. Nada é perdido.

## 9. Falhas e resiliência

**O build é atômico.** Qualquer etapa que falhe aborta o job sem commit, e o
site segue servindo o catálogo do dia anterior. Publicar meio catálogo é pior
que publicar um catálogo velho.

| Falha | Resposta |
|---|---|
| TMDB indisponível ou limitando | Retry com espera exponencial; esgotado, aborta sem commit |
| Export diário de ids indisponível | Fallback para `/discover` ordenado por data de lançamento |
| Filme removido do TMDB | Sai do catálogo; permanece no perfil como registro órfão |
| Escrita concorrente no perfil | Merge por filme, `at` mais recente vence, até 3 tentativas |
| Token inválido | Aviso ao autor, retenção local das avaliações |
| Perfil vazio | Onboarding |
| Falha silenciosa do Actions | O workflow abre uma issue no repositório |

## 10. Limites aceitos

Escolhas, não defeitos:

- **Sem séries.**
- **Recomendação baseada em conteúdo, não colaborativa.** O sistema diz "isso
  se parece com o que você gosta", nunca "quem gostou disso também gostou
  daquilo". O segundo exigiria dados de milhares de usuários que não existem
  aqui. O custo é um motor mais previsível e menos capaz de surpresas felizes;
  as fileiras 9 e 10 mitigam, não eliminam.
- **Cobertura irregular de keywords no TMDB.** Mitigada pela redistribuição de
  peso, não resolvida.
- **Bolha de gosto.** Mitigada, não eliminada.
- **Um usuário.** Não há multiusuário nem perfis.

## 11. Testes

O motor de pontuação é a única parte onde um erro é invisível — um ranking ruim
não quebra nada, apenas decepciona. Os testes se concentram nele.

- Perfil sintético produz a afinidade esperada, com valores conferidos à mão
- A normalização por raridade funciona: `drama` pesa menos que `post-apocalyptic`
- Filme sem keywords não é penalizado — a redistribuição de peso ocorre
- Parser de `release_dates` classifica corretamente casos reais capturados
- Fatiamento por ano dispara quando o `/discover` estoura 10 mil resultados
- Merge do perfil sob conflito preserva a marcação mais recente por filme
- Regras de admissão: graduação e expiração da trilha *Recente*
- **Teste de tamanho:** o build falha se `site/data/index.json` passar do limite
  configurado. Impede degradação silenciosa do carregamento

Respostas do TMDB ficam gravadas como fixtures. A CI não depende da API.

## 12. Stack

| Camada | Escolha | Motivo |
|---|---|---|
| Pipeline | Python 3.12, `httpx` async, `pytest` | mesma base dos outros projetos do autor |
| Site | HTML, CSS e JavaScript com módulos ES | filtrar 40 mil registros em JS puro é instantâneo; um framework custaria uma toolchain para resolver um problema inexistente |
| Cron | GitHub Actions | gratuito em repositório público |
| Hospedagem | GitHub Pages | gratuita |
| Chave da API | segredo do repositório no Actions | nunca no cliente |

**Atribuição obrigatória.** Os termos do TMDB exigem a nota, visível no rodapé:
*"Este produto usa a API do TMDB, mas não é endossado nem certificado pelo
TMDB."* Acompanhada do logo.

## 13. Ordem de construção sugerida

Cada etapa entrega algo verificável sozinho. A ordem existe porque o motor não
pode ser avaliado sem catálogo, e a interface não pode ser avaliada sem motor.

1. **Cliente TMDB e carga inicial** — `fetch.py` mais regras de admissão,
   produzindo um `catalog.jsonl` real. Verificável: o arquivo existe, tem o
   volume esperado e passa nos testes de admissão.
2. **Motor de pontuação** — `score.py` sobre um perfil sintético. É a etapa de
   maior risco e a mais testável isoladamente. Verificável pelos testes de
   afinidade e de redistribuição de peso.
3. **Build e fileiras** — `shelves.py` e `build.py` gerando `site/data/`.
   Verificável: os arquivos abrem e as fileiras têm conteúdo plausível.
4. **Interface** — home, grade e ficha, lendo os artefatos já prontos.
5. **Escrita do perfil** — token, lote, merge de conflito.
6. **Automação** — workflow do Actions, cron, issue em caso de falha.

O onboarding depende de 4 e 5, e fecha o ciclo: a partir dele o motor passa a
ter dados reais.

## 14. Pendências de configuração

Não bloqueiam a implementação; são valores a preencher.

1. Token de leitura da API do TMDB — gerar em themoviedb.org e cadastrar como
   segredo `TMDB_TOKEN` no repositório.
2. Token do GitHub de escopo restrito, para a escrita do perfil pelo navegador.
   Só é necessário na etapa 5 da ordem de construção.
3. Piso de `popularity` da trilha *Recente* — calibrar com dados reais na
   primeira carga.
4. Limite de tamanho do `index.json` para o teste de regressão.
5. Conteúdo inicial de `vibes.json` — as ~250 expressões.
