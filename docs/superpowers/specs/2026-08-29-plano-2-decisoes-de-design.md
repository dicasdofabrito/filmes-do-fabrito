# Plano 2 (o site) — decisões de design que o spec original deixou em aberto

**Data:** 29 de agosto de 2026
**Autor:** Claude, sozinho — Fabio autorizou execução noturna autônoma e foi
dormir. Este documento registra as decisões tomadas em seu lugar antes da
implementação, no mesmo espírito do registro de decisões da execução do
Plano 1 (`2026-08-28-decisoes-da-execucao.md`), mas escrito **antes** de
codificar, porque são decisões de planejamento, não correções de bug.

O spec original (`2026-08-27-filmes-do-fabrito-design.md`) descreve **o que**
o site faz, mas várias peças de **como** ele funciona de verdade só ficam
visíveis ao tentar montar o cliente contra os artefatos que o pipeline
realmente publica. Cada decisão abaixo tem o problema, a escolha, e o custo
se estiver errada.

---

## 1. Hospedagem: GitHub Pages servindo a raiz do repositório

**Problema.** O spec diz "GitHub Pages serve o site", sem detalhar a
configuração. GitHub Pages, no modo "deploy from branch", só serve `/` (raiz)
ou `/docs` — nunca uma subpasta arbitrária como `/site`. Se eu tentasse servir
só `/site` via um workflow de deploy por artefato (`actions/deploy-pages`),
`data/catalog.jsonl`, `data/vibes.json` e `data/nomes.json` — que vivem fora
de `site/` — ficariam inacessíveis ao cliente, quebrando a ficha do filme, a
busca por vibe e os nomes de diretor/elenco.

**Decisão.** Pages configurado como **Deploy from branch: master, pasta `/`
(raiz)**. Isso serve o repositório inteiro, então `site/index.html` fica
acessível e todo fetch do cliente para `data/*` funciona com caminho relativo
simples, sem workflow de deploy adicional — todo push em `master` já
republica sozinho, sem custo extra de infraestrutura, batendo com o espírito
minimalista do spec ("sem servidor, sem banco hospedado").

**Ação pendente que só o Fabio pode fazer.** Habilitar isso é uma mudança de
configuração do repositório (Settings → Pages → Source: Deploy from branch →
master → / (root) → Save), dois cliques. Não faço isso sozinho: é alteração
de configuração de conta/repositório, fora do que a autorização de trabalhar
a noite cobre. Fica registrado como o único passo manual restante.

**Custo se errado.** Nenhum dado sensível fica exposto — o repositório já é
público por decisão anterior do spec. Se Fabio preferir uma URL customizada
ou outro esquema depois, é reconfigurável a qualquer momento sem tocar em
código.

---

## 2. `poster_path` ausente de `index.json`

**Problema.** O spec (seção 4.4) diz que `index.json` é o arquivo "enxuto de
navegação e ranking" e deliberadamente **não** carrega pôster nem sinopse,
que ficam só em `catalog.jsonl`. Isso faz sentido para sinopse (~300
caracteres por filme, pesado). Mas a home (seção 7.1, prateleiras) e a grade
(7.2) são interfaces **visuais** — pôsteres em fileiras e grade, confirmado
pelos mockups aprovados na fase de brainstorming ("C · Prateleiras
temáticas" com miniaturas de pôster). Sem `poster_path` em `index.json`, a
home não teria como mostrar nenhum pôster sem buscar `catalog.jsonl` por
filme individualmente — inviável para uma tela com centenas de pôsteres
visíveis de uma vez.

**Decisão.** Adiciono `p` (poster_path) a `index.json`. Custo de tamanho:
~33 caracteres por filme × 36.540 filmes ≈ 1,2–1,5 MB. Medido hoje o
`index.json` real tem 5,17 MB; com esse campo sobe pra ~6,7 MB, ainda
confortavelmente abaixo do `limite_index_mb` de 12 MB. Sinopse continua fora
— essa, sim, só pela ficha via `catalog.jsonl`.

**Custo se errado.** Se o índice crescer demais no futuro (catálogo maior),
o teste de tamanho do CI (`IndiceGrandeDemais`) pega isso automaticamente —
é exatamente pra isso que ele existe.

---

## 3. Como a ficha do filme lê uma linha de `catalog.jsonl` sem baixar 21 MB

**Problema.** O spec (4.4) diz literalmente: "o site busca esse arquivo
também, mas só a linha do filme aberto, nunca o arquivo inteiro". Isso é
HTTP Range request — mas o spec nunca definiu como o cliente sabe o offset
em bytes de cada filme dentro do arquivo. Sem esse índice, a única forma de
"pegar só uma linha" seria baixar o arquivo inteiro e cortar — o que o spec
explicitamente proíbe.

**Decisão.** O pipeline passa a publicar `site/data/offsets.json`: um mapa
`{"<id>": [inicio_byte, fim_byte]}` calculado a partir do `catalog.jsonl`
recém-escrito. O cliente faz um `fetch` com header `Range: bytes=inicio-fim`
para `data/catalog.jsonl`, pegando só a linha desejada. GitHub Pages (servido
via Fastly) suporta Range requests de forma confiável em arquivos estáticos —
é a mesma técnica usada por bibliotecas como `sql.js-httpvfs` contra hosts
estáticos. Como salvaguarda: se a resposta não vier com status 206 (Range não
suportado ou ignorado por algum motivo), o cliente cai para tratar o corpo
recebido como o arquivo inteiro e localizar a linha por offset/quebra de
linha, em vez de quebrar.

Tamanho de `offsets.json`: ~15 bytes por entrada (dois inteiros) × 36.540 ≈
550 KB — leve, carregado uma vez e mantido em memória.

**Custo se errado.** Se Range request falhar na prática por algum motivo
específico do GitHub Pages, o fallback busca o arquivo inteiro só naquela
tentativa — funciona, só fica mais lento. Não é um caminho que quebra a
ficha do filme, só degrada a velocidade dela nesse cenário hipotético.

---

## 4. Nomes de diretor/elenco existem; nomes de keyword e gênero, não

**Problema.** `data/nomes.json` já mapeia id de diretor/ator → nome (criado
no Plano 1 para os títulos das fileiras "Mais de X"/"Com X"). Mas a ficha do
filme (7.3) também precisa mostrar **keywords** e a grade (7.2) precisa
filtrar por **gênero** — nenhum dos dois tem nome publicado em lugar nenhum,
só o id numérico do TMDB.

**Decisão, gêneros:** o TMDB tem só ~19 gêneros de filme, uma lista estável
que quase nunca muda. Busco a lista oficial em pt-BR uma vez
(`/genre/movie/list`) e commito como `data/generos.json` estático — não
precisa de nova dependência recorrente no pipeline.

**Decisão, keywords:** ao contrário de gênero, não existem "todas as
keywords do TMDB" como lista fechada — são potencialmente dezenas de
milhares, uma por filme. Mas o nome de cada keyword **já vem** na mesma
resposta de `/movie/{id}` que o pipeline usa pra pegar o id (`detalhe["keywords"]["keywords"]`
é uma lista de `{"id":.., "name":..}`), e hoje o `montar_filme` descarta o
nome, guardando só o id. Estendo `data/nomes.json` com um terceiro balde
`"keyword"`, populado no mesmo loop que já busca detalhes — **zero chamada
de API a mais**, só para de jogar fora um dado que já chega de graça.

**Consequência aceita.** Filmes que entraram no catálogo antes dessa mudança
só ganham nome de keyword na próxima vez que forem reprocessados (quando
saem da trilha "recente", ou nunca, se já são "acervo" e nenhuma keyword
sua aparece de novo). O cliente degrada mostrando o chip sem nome (ou
omitindo) quando o nome não está em `nomes.json` — nunca quebra a ficha.

---

## 5. Atribuição do TMDB exige o logo, não só o texto

**Problema.** Spec seção 12: o texto de atribuição "acompanhada do logo".
Preciso do arquivo de fato, não só uma URL de terceiro linkada ao vivo (mais
frágil — hashes de asset do TMDB mudam entre deploys deles).

**Decisão.** Uma task busca o logo oficial atual do TMDB (via ferramenta de
navegador) e salva local em `site/assets/tmdb-logo.svg`, versionado no
repositório — igual a qualquer app que legitimamente usa a marca deles sob
os termos de atribuição.

---

## 6. Testes de um site sem framework e sem etapa de build

**Problema.** O spec exige "sem framework, sem etapa de build" (seção 12).
Isso deixa de fora bundlers e, por extensão, a infraestrutura usual de teste
de front-end que depende deles (Jest com jsdom via transform, Vitest, etc.).
O projeto inteiro até aqui seguiu TDD rigoroso — preciso de um jeito de
manter isso sem contradizer a restrição.

**Decisão.** Separação de responsabilidade dita a estratégia de teste:

- **Módulos de lógica pura** (`store.js`, `vibes.js`, `github.js`,
  `router.js`, `onboarding.js`) — sem DOM, só dados entrando e saindo — são
  testados com o test runner nativo do Node (`node:test` + `node:assert`),
  zero dependência instalada. `site/package.json` só declara
  `{"type":"module"}`, para o Node tratar `.js` como ES module tanto nos
  testes quanto no navegador.
- **Módulo de renderização** (`ui.js`) manipula DOM diretamente. Não trago
  `jsdom` só pra isso — seria a exata dependência de build/teste que o spec
  pede pra evitar. Cada função de `ui.js` é verificada visualmente via a
  ferramenta de navegador (screenshot + leitura da árvore de acessibilidade),
  não por asserção unitária. Isso é registrado explicitamente para os
  implementadores não tentarem forçar um `jsdom` por conta própria.

**Custo se errado.** Se `ui.js` crescer lógica demais escondida atrás de
manipulação de DOM, put isso viraria um ponto cego de teste real. Mitigação:
qualquer decisão (o que mostrar, como ordenar, o que filtrar) fica em
`store.js`/lógica pura testável; `ui.js` só recebe dados já prontos e
desenha.

---

## 7. "O que mais se parece com esse" exige uma fatia do motor em JavaScript

**Problema.** A ficha do filme (7.3) tem a ação "o que mais se parece com
esse" — a mesma maquinaria de `gosto_de_um_filme` (6.4), mas para um filme
**qualquer** que o Fabio esteja olhando naquele momento, não só o último
curtido (que é o que a fileira 3 da home já resolve, pré-computada). Como
não existe servidor pra consultar sob demanda ("sem servidor" é restrição
dura do spec), a única forma de essa ação funcionar é calcular no cliente.

**Decisão.** Porto fielmente `afinidade()`/`qualidade_bayesiana()`/`_pesar()`
de `sync/score.py`/`sync/profile.py` para `site/js/motor.js`, mesma fórmula,
mesmos pesos (lidos de `config.json`, alcançável pelo cliente pela decisão
#1 de hospedagem na raiz). Isso exige publicar em `index.json` os campos que
faltavam pra replicar o cálculo: `d` (diretores), `c` (elenco) e `l`
(idioma) — hoje só em `catalog.jsonl`. Custo de tamanho: ~1,7 MB somados,
levando o índice a ~8,4 MB — ainda dentro do limite de 12 MB, mas consumindo
parte real da folga que a calibração deixou pra crescimento do catálogo, não
pra isso. Vale revisitar se o catálogo crescer bastante.

**Custo se errado.** Duas implementações da mesma fórmula, em duas
linguagens, precisam ser mantidas em sincronia manualmente se os pesos do
`config.json` mudarem um dia — registro isso como limite aceito, no mesmo
espírito da seção 10 do spec original.

## 7.1. Correção: `fetch()` resolve contra o documento, não contra o módulo

**Problema descoberto durante a implementação.** Ao escrever os briefs das
tasks 5, 8, 11 e 12, tratei caminhos relativos em chamadas `fetch()` como se
resolvessem contra a localização do arquivo `.js` que faz a chamada — o jeito
como `import` funciona em módulos ES. Não é assim: `fetch()` (como qualquer
URL relativa em HTML/JS fora de `import`) resolve contra `document.baseURI`,
ou seja, a URL da própria página (`site/index.html`, cuja base efetiva é
`.../site/`), **não** contra `site/js/store.js` ou qualquer outro arquivo
que faça a chamada.

Isso inverteu a contagem de `../` em vários lugares:
- Arquivos que o **próprio build do site** gera, irmãos de `index.html`
  (`site/data/index.json`, `shelves.json`, `offsets.json`, `keywords.json`):
  caminho sem `../` nenhum — `"data/index.json"`.
- Arquivos que vivem na **raiz do repositório** (`data/vibes.json`,
  `data/nomes.json`, `data/generos.json`, `data/catalog.jsonl`,
  `config.json`): um único `../` a partir de `site/js/qualquer-arquivo.js`,
  porque a base efetiva já é `site/`, não `site/js/`.

Confirmado experimentalmente com `new URL(caminho, "https://.../site/").href`
antes de corrigir os briefs, não só por dedução.

**Onde o erro apareceu e como foi resolvido:**
- `store.js` (Task 5, já implementada): `CAMINHO_INDICE`/`CAMINHO_FILEIRAS`
  tinham `../` de sobra — corrigido via fix round depois de detectado durante
  a verificação visual da Task 9 (o bug ficou mascarado localmente porque o
  servidor de preview usado servia `site/` como raiz, e `..` acima da raiz do
  servidor simplesmente trava na própria raiz — coincidindo, por acidente,
  com o caminho certo. Em produção, com o repositório inteiro servido, não
  haveria essa coincidência).
- `vibes.js` (Task 8): já estava correto por acaso (o arquivo que ele busca
  é da raiz do repositório, então o único `../` que eu tinha escrito era o
  certo).
- Tasks 11 e 12 (ainda não implementadas no momento da descoberta): código do
  plano corrigido antes do brief ser gerado — `offsets.json` perdeu o `../`
  que não devia ter, `config.json` perdeu um `../` a mais que não devia ter.

**Custo se essa correção estiver errada:** nenhum caminho a mais nem a menos
muda o comportamento fora do cenário exato que ela resolve; testei a
resolução real via `new URL()` no navegador antes de aplicar.

## 8. Persistência do token do GitHub

O Fabio nunca me entrega o próprio token de escrita — nem eu peço. A UI de
colar o token (spec seção 8) é testada com um token FALSO nos testes
automatizados; a verificação de escrita real no repositório fica para o
Fabio testar manualmente de manhã, colando o token dele mesmo na página
publicada.
