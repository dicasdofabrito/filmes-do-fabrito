> Registro das decisões tomadas durante a execução automatizada do Plano 1.
> Preservado do ledger de execução. Cada linha "Ruling:" é uma decisão tomada
> sem consultar o Fabio, com o custo anotado caso esteja errada.

# SDD ledger — plan: docs/superpowers/plans/2026-08-27-filmes-do-fabrito-pipeline.md

Spec: docs/superpowers/specs/2026-08-27-filmes-do-fabrito-design.md (lido)
Worktree: C:\Users\fabio\Claude local\filmes-do-fabrito-pipeline (branch `pipeline`, base 67aa4eb)

## Pré-voo: varredura de conflitos

### Pares que compartilham arquivo ou interface

| Produtor | Consumidor | Contrato | Achado |
|---|---|---|---|
| T1 `TMDBClient.get` | T2 `paginar`, `descobrir_fatiado` | `get(path, **params) -> dict` | consistente |
| T1 `TMDBClient.get` | T11 `buscar_detalhes` | idem | consistente |
| T2 `descobrir_fatiado(cliente, params, *, ano_inicial=1874, ano_final)` | T11 `_ids_para_processar` chama com `ano_final=hoje.year` | kw-only obrigatório presente | consistente |
| T3 `baixar_export`, `ids_novos` | T11 `_ids_para_processar` | `set[int]` nos dois lados | consistente |
| T4 `Config/Admissao/Motor/Build` | T7, T8, T9, T10, T11 | ordem posicional dos campos usada nos testes de T8/T9 bate com a ordem dos dataclasses | consistente |
| T4 `classificar(detalhe, hoje, cfg)` | T11 | assinatura idêntica | consistente |
| T5 `apenas_no_cinema(release_dates, hoje)` | T11 | T11 passa `detalhe["release_dates"]`, que vem do `append_to_response` de T11 | consistente |
| T6 `Movie`, `montar_filme`, `ler/escrever_catalogo` | T7, T8, T9, T10, T11 | 14 campos; `montar_filme(detalhe, *, track, theatrical, added)` | consistente |
| T7 `features_of`, `Taste` | T8 `afinidade`, T9 `_ponto_cego`/`_por_pessoa` | chaves `keyword/director/cast/genre/decade/language` idênticas em T7, T8 (pesos) e T4 (config.json) | consistente |
| T7 `gosto_de_um_filme` | T9 `_similar` | consistente |
| T8 `Scoring`, `afinidade` | T9 `Contexto.pontuacao`, T10 | `scores/affinities/qualities` usados nos três | consistente |
| T9 `Shelf`, `Contexto`, `montar_fileiras` | T10 `escrever_site_data`, T11 | `Shelf(key, title, movie_ids)` posicional em T10 bate | consistente |
| T10 `escrever_site_data(destino, catalogo, pontuacao, fileiras, cfg)` | T11 | consistente |

### Autoconsistência de cada task

| Task | Testes x código especificados | Achado |
|---|---|---|
| T1 | 4 testes cobrem auth, retry, desistência, erro definitivo | consistente |
| T2 | teste de fatiamento usa sondagem `total_results=12000` que a implementação lê antes de paginar | consistente |
| T3 | teste de gzip/JSONL bate com `gzip.decompress` + `splitlines` | consistente |
| T4 | 11 testes; `config.json` real é lido pelos testes (não fixture) — acopla teste a config de produção, aceito de propósito para detectar edição inválida | consistente |
| T5 | 6 testes incluem datas futuras nos dois lados; implementação ignora `> hoje` | consistente |
| T6 | `to_row`/`from_row` simétricos nos 14 campos | consistente |
| T7 | 9 testes; asserção de suavização corrigida para `pytest.approx` na autorrevisão do plano | consistente |
| T8 | teste central da redistribuição confere 1.0 nos dois filmes | consistente |
| T9 | `_cfg` do teste usa `Build(6.0, 3)` e o teste de tamanho espera 3 | consistente |
| T10 | escreve `index.json` antes de checar tamanho; aceitável porque só existe em diretório temporário | consistente |
| T11 | **DOIS DEFEITOS — ver rulings abaixo** | ver abaixo |

### Rulings do pré-voo

**Ruling 1: a carga inicial do plano buscaria detalhes de ~900 mil filmes.**
O `_ids_para_processar` em modo `--carga-inicial` chama `descobrir_fatiado` sem
filtro de qualidade, devolvendo o acervo inteiro do TMDB; em seguida
`buscar_detalhes` é chamado para todos os ids desconhecidos, antes de qualquer
regra de admissão. Isso são ~900 mil requisições, não as 40 mil que a estimativa
de "15 a 40 minutos" do Step 8 pressupõe — horas de execução para descartar 95%
do resultado. Decidido: a carga inicial passa `vote_count.gte` igual a
`min_votos_acervo` nos parâmetros do `/discover` (o TMDB suporta esse filtro
nativamente), e faz uma segunda varredura separada só da janela recente, com
`primary_release_date.gte` em `meses_recente` atrás. O filtro de admissão
continua valendo depois, como rede. *Custo se errado:* a carga inicial pode
perder filmes de fronteira que o `vote_count` do índice do discover reporta
desatualizado; corrigível numa reexecução sem perder nada.

**Ruling 2: a graduação da trilha *Recente* nunca aconteceria.**
O spec (seção 5.1) diz que um filme da trilha *Recente* que acumular 50 votos em
18 meses gradua para *Acervo* permanentemente. Mas o pipeline só busca detalhes
de ids **novos** — um filme já no catálogo nunca tem `vote_count` reatualizado,
então `track` fica congelado no valor do dia da admissão e a graduação é código
morto. Pior: a poda por `added` expulsaria em 18 meses um filme que já deveria
ter graduado. Decidido: a cada execução, o pipeline rebusca os detalhes de todos
os filmes com `track == "recente"` (são poucos milhares) e os reclassifica,
atualizando também `theatrical` — que é justamente o campo que mais muda com o
tempo e que, sem isso, deixaria filmes presos em "Nos cinemas" para sempre.
*Custo se errado:* alguns milhares de requisições a mais por dia, dentro de
folga larga; se a decisão estiver errada o desperdício é de tempo de execução,
não de correção.

Ambos os rulings entram no dispatch da Task 11.

## Progresso

Task 1: implementada (commit fa1c618, 4 testes passando) — revisão despachada
Task 1: nota — o worktree não tinha identidade git; o implementador configurou
  user.name/user.email localmente (escopo do repositório). Consistente com os
  commits anteriores do projeto. Sem ação.
Task 1: revisão — Spec OK, qualidade aprovada. 2 Important, 2 Minor.
Task 1: Ruling: identificadores em português apontados como violação da
  constraint global — a constraint estava errada, não o código. O plano inteiro
  usa vocabulário de domínio em português (`classificar`, `montar_filme`,
  `descobrir_fatiado`); a regra "identificadores em inglês" contradizia o
  próprio plano que eu escrevi e faria todo revisor futuro reabrir a mesma
  discussão em 10 tasks. Emendei a constraint para descrever o que o código de
  fato faz: português no domínio, inglês só nos campos de `Movie` (que espelham
  o contrato JSON do site) e onde o nome reproduz campo da API do TMDB.
  Sem mudança de código. *Custo se errado:* código bilíngue por convenção
  explícita em vez de acidente — reversível com um rename mecânico.
Task 1: minor (deferred): último `asyncio.sleep` executa antes de desistir,
  desperdiçando ~8s em produção na falha final (sync/tmdb.py, fim do laço).
Task 1: minor (deferred): crescimento exponencial do backoff nunca é exercitado
  — todos os testes fixam backoff_base=0.0.
Task 1: fix round 1/5 (1 tratado, 0 abertos — teste do Retry-After tornado
  não-vacuoso, mais teste do crescimento exponencial; implementador confirmou
  que o novo teste falha quando o código do Retry-After é desabilitado;
  commits fa1c618..1599fc6) — re-revisão escopada despachada
Task 1: emenda da constraint de idioma commitada em 541380a
Task 1: complete (commits 67aa4eb..1599fc6, review clean após 1 fix round)
Task 2: implementada (commit a2f77df, 9 testes passando no total) — revisão despachada
Task 2: revisão — Spec OK, qualidade aprovada. 1 Important, 2 Minor.
Task 2: Ruling: o caso-base `ano_inicial >= ano_final` do meu brief pagina com
  teto de 500 páginas quando um único ano estoura 10 mil resultados, perdendo o
  excedente em silêncio — o exato modo de falha que a task existe pra evitar.
  Decidido consertar em vez de parquear: a recursão passa a bissectar intervalo
  de DATAS (ano -> mês -> dia) por baixo, mantendo a assinatura pública
  `descobrir_fatiado(cliente, params, *, ano_inicial, ano_final)` que a Task 11
  consome. Só no piso de um único dia o teto é aceito, e aí com aviso explícito.
  *Custo se errado:* recursão mais profunda e algumas requisições de sondagem a
  mais; nenhum risco de perda de dado, que era o ponto.
Task 2: minor (deferred): nenhum teste exercita split de 3+ níveis.
Task 2: minor (deferred): `descobrir_fatiado` fixa "/discover/movie" em vez de
  aceitar `path` como `paginar` faz — consistente com a assinatura acordada.
Task 2: fix round 1/5 (1 tratado, 0 abertos — recursão passou a bissectar datas,
  piso de um dia com aviso em log; commits a2f77df..d735e98, 11 testes)
  — re-revisão escopada despachada
Task 2: complete (commits 541380a..d735e98, review clean após 1 fix round)
Task 2: minor (deferred): mojibake em mensagem de assert (tests/test_discover.py:146)
Task 2: minor (deferred): `import pytest` não usado (tests/test_discover.py:2)
Task 3: implementada (commit ef4f1b2, 14 testes passando) — revisão despachada
Task 3: complete (commits d735e98..ef4f1b2, review clean, zero achados)
Task 4: implementada (commit 1a3eea8, 25 testes passando) — revisão despachada
Task 4: revisão — Spec OK, qualidade aprovada. 2 Important (lacunas de teste), 2 Minor.
Task 4: Ruling: as duas lacunas de teste (data de lançamento futura; fronteira
  da janela de 540 dias) vão para conserto em vez de adiadas. A lógica está
  correta hoje, mas admissão é irreversível — filme rejeitado aqui não aparece
  em lugar nenhum do produto e nada a jusante recupera. Sem teste, uma refatoração
  futura que troque `>= 0` por `abs()` passa despercebida. *Custo se errado:*
  dois testes a mais numa suíte barata.
Task 4: Minor corrigido pelo controller: a prosa "Interfaces" do meu plano listava
  os campos de `Motor` fora de ordem, divergindo do próprio código do plano e do
  que as Tasks 8/9 constroem posicionalmente. Corrigido no plano (commit abaixo);
  o código enviado já estava certo.
Task 4: minor (deferred): `release_date` não-string e truthy levantaria TypeError
  não capturado em _data_de (sync/admission.py:78-82); TMDB sempre manda string.
Task 4: fix round 1/5 (2 tratados, 0 abertos — 3 testes novos: lançamento futuro,
  fronteira dia 540 e dia 541; implementação intocada; commits 1a3eea8..cf2a688,
  28 testes) — re-revisão escopada despachada
Task 4: complete (commits ef4f1b2..cf2a688, review clean após 1 fix round)
Task 5: implementada (commit 921f294, 34 testes passando) — revisão despachada
Task 5: complete (commits cf2a688..921f294, review clean, 1 Minor adiado)
Task 5: minor (deferred): 4 testes que esperam False passariam contra um stub
  `return False`; falta um caso "lançamento doméstico sem estreia em sala" para
  discriminar o AND da regra (tests/test_theatrical.py).
Task 6: implementada (commit 7ba359e, 40 testes passando) — revisão despachada
Task 6: complete (commits 921f294..7ba359e, review clean, 2 Minor adiados)
Task 6: minor (deferred): linha corrompida no catalog.jsonl aborta a leitura
  inteira em vez de pular (sync/catalog.py:218-223) — comportamento defensável,
  mas não é escolha consciente registrada.
Task 6: minor (deferred): testes de `montar_filme` não conferem genres, runtime,
  vote_average, vote_count nem language (tests/test_catalog.py:190-215).
Task 7: implementada (commit 80d37c9, 49 testes passando) — revisão despachada
Task 7: complete (commits 7ba359e..80d37c9, review clean, 3 Minor adiados)
Task 7: nota matemática — característica presente em 100% do catálogo gera idf
  negativo (log(N/(N+1))), podendo dar peso levemente negativo a algo curtido.
  Revisor calculou o limite: |efeito| <= ~1/N, ~0,002 em 40 mil filmes. Aceito.
Task 7: minor (deferred): `decade` usa checagem falsy em vez de `is not None`;
  year == 0 daria tupla vazia (sync/profile.py:217). Sem filme real afetado.
Task 7: minor (deferred): `ler_perfil` levanta exceção em entrada malformada em
  vez de degradar; não especificado nem testado nos dois sentidos.
Task 7: minor (deferred): test_caracteristica_presente_em_todo_o_catalogo passaria
  contra um stub que devolve 0.0 sempre; a cobertura real vem de outros dois testes.
Task 8: implementada (commit f051eaf, 58 testes passando) — revisão despachada
Task 8: revisão — Spec OK, aritmética sólida. 2 Important, 3 Minor.
  Teste-guarda da redistribuição verificado à mão: 1,0 (redistribuído) vs 0,15
  (ingênuo) — o guarda guarda de verdade.
Task 8: parked — "filme odiado mas aclamado pode superar filme neutro e mediano"
  — Ruling: a descrição da fórmula está correta, mas o contraexemplo do revisor
  usa qualidade 0,0, que a suavização bayesiana torna inatingível (tudo é puxado
  para a média global, faixa real ~0,55-0,85). O código fica como está.
  *Custo se errado:* se na prática aparecerem recomendações que o Fabio odeia,
  a correção é baixar `peso_afinidade` no config — parâmetro, não arquitetura.
Task 8: Ruling: o guard `amplitude = (maior - menor) or 1.0` está errado por
  construção. Quando toda afinidade empata, a informação de afinidade é nula, e
  a degradação correta é score = qualidade — não 0,25 x qualidade, que é o que
  acontece hoje. Só dispara com catálogo de 1 filme ou empate perfeito, ou seja
  nunca em 40 mil filmes; mesmo assim vai para conserto porque é uma linha, e
  este é o módulo de maior risco do projeto. Junto vai o Minor da tolerância de
  ponto flutuante, que é a mesma linha. *Custo se errado:* uma linha revertível.
Task 8: minor (deferred): 2 testes fracos (afinidade zero; score em [0,1])
  passariam contra stub constante; os outros 7 discriminam.
Task 8: minor (deferred): cópia defensiva assimétrica no ramo de partida a frio
  (sync/score.py:83-85) — inofensivo, Scoring é frozen.
Task 8: fix round 1/5 (1 tratado, 0 abertos — guard de amplitude com tolerância
  1e-12 e degradação para qualidade pura; implementador confirmou por reversão
  temporária que os 2 testes novos ficam vermelhos com a linha antiga;
  commits f051eaf..edab513, 60 testes) — re-revisão escopada despachada
Task 8: complete (commits 80d37c9..edab513, review clean após 1 fix round)
Task 9: implementada (commit 3d7731e, 70 testes) — implementador sinalizou que
  `aposta` e `ponto_cego` não têm teste direto. Revisão despachada com isso
  explicitado.
Task 9: revisão — Spec OK. 3 Important, 3 Minor. Revisor confirmou por reprodução
  com catálogo sintético que `aposta`/`classicos`/`ponto_cego` podem esvaziar.
Task 9: Ruling: o corte de qualidade dessas três fileiras é calculado sobre o
  catálogo INTEIRO (incluindo vistos) enquanto os candidatos são só os NÃO vistos
  — a régua é definida por filmes inelegíveis. O modo de falha piora com o uso:
  quanto mais o Fabio assiste os melhores, mais o topo da distribuição vira
  "visto" e mais inalcançável fica a barra; e como fileira vazia é omitida, a
  linha some sem sinal. É o oposto do propósito das três. Decidido consertar:
  o percentil passa a ser calculado sobre a população elegível de cada fileira.
  Junto vão as duas lacunas de teste (aposta/ponto_cego sem teste direto; nenhum
  teste fornece qualities/affinities não-uniformes, então `_percentil` e a
  ordenação de `_ordenar` nunca são exercitados de verdade).
  *Custo se errado:* as três fileiras passam a devolver sempre ~2-5% do elegível
  em vez de possivelmente nada — mais generoso, nunca mais restrito.
Task 9: minor (deferred): teste da vibe prova repetibilidade, não dependência da
  data; uma seleção fixa passaria igual (tests/test_shelves.py).
Task 9: minor (deferred): `_classicos` exclui por `not in perfil.movies` enquanto
  as demais excluem só por visto — intencional e spec'd, mas inconsistente.
Task 9: minor (deferred): desempate de `_similar` em curtidas de mesma data cai
  no maior id, sem critério deliberado (sync/shelves.py:88-90).
Task 9: fix round 1/5 (3 tratados, 0 abertos — corte por população elegível nas
  3 fileiras, testes diretos de aposta/ponto_cego incluindo o gate de 200, e
  contexto de teste com qualities/affinities não-uniformes; reversão temporária
  confirmou que as 2 fileiras somem com o código antigo; commits 3d7731e..55667f5,
  75 testes) — re-revisão escopada despachada
Task 9: complete (commits edab513..55667f5, review clean após 1 fix round)
Task 9: minor (deferred): `similar`, `vibe`, `diretor` e `ator` seguem sem teste
  direto (levantado pelo re-revisor como fora de escopo daquele fix).
Task 10: implementada (commit 58f6328, 80 testes) — revisão despachada
Task 10: complete (commits 55667f5..58f6328, review clean, 2 Minor adiados)
Task 10: minor (deferred): nenhum teste exercita `destino` inexistente de fato
  (tmp_path já existe); e nenhum confere que filme sem keyword não gera entrada.
Task 11: Ruling de escopo: o implementador faz apenas os Steps 1-7 (código,
  testes, commit). Os Steps 8-10 (carga inicial real, calibração do piso de
  popularidade, commit do catálogo) ficam comigo e com o Fabio: exigem o token
  dele, levam 15-40 min contra a API e o resultado precisa ser inspecionado por
  um humano antes de virar dado do projeto. *Custo se errado:* nenhum — é
  sequenciamento, não mudança de conteúdo.
Task 11: implementada (commit 6603ad8, 90 testes; Steps 8-10 deliberadamente não
  executados) — revisão despachada
Task 11: revisão — Spec OK (as 2 correções implementadas). 2 CRITICAL, 4 Important.
Task 11: Ruling: os 2 Critical de atomicidade vão para conserto. `publicar_atomico`
  apaga-e-move (se morrer no meio, site/data some inteiro — pior que servir o de
  ontem) e `escrever_catalogo` grava direto no arquivo real entre a escrita segura
  e a publicação. A atomicidade é a regra que eu declarei governar a task inteira;
  não posso fechá-la com a garantia falsa. *Custo se errado:* uma pasta de backup
  temporária a mais durante a troca.
Task 11: Ruling: o 404 permanente que trava o pipeline vai para conserto, e não é
  robustez opcional — o spec (seção 9) já mandava "filme removido do TMDB sai do
  catálogo e permanece no perfil como registro órfão". O plano nunca implementou.
  É lacuna de cobertura do spec. *Custo se errado:* um filme que o TMDB devolva
  404 transitoriamente sairia do catálogo e voltaria no dia seguinte.
Task 11: Ruling: os nomes de diretor/ator vão para conserto via `data/nomes.json`
  persistido e mesclado a cada execução. Sem isso, a fileira "Mais de X" mostra
  um id numérico cru sempre que o filme daquele diretor já graduou para acervo —
  garantido de acontecer, e visível na home. *Custo se errado:* um arquivo JSON
  pequeno a mais no repositório.
Task 11: Ruling: diretórios temporários órfãos a cada falha vão junto (try/finally),
  por serem a mesma região de código.
Task 11: fix round 1/5 (5 tratados, 0 abertos — troca por renomeação com backup,
  catálogo via os.replace, 404/410 remove do catálogo preservando o perfil,
  data/nomes.json persistido, temporários em try/finally; commits 6603ad8..5f63dfc,
  96 testes) — re-revisão escopada despachada
Task 11: complete (commits 58f6328..5f63dfc, review clean após 1 fix round)
Task 11: parked — `_escrever_nomes` grava data/nomes.json direto, sem temp+replace,
  e fora do try/finally. Crash no meio deixaria JSON corrompido, que faria o
  `_carregar_nomes` da próxima execução levantar — mesmo padrão de travamento
  permanente que o achado 3 eliminou. Ruling: Minor pelo revisor e exige crash
  exatamente no meio da escrita de um arquivo pequeno; NÃO entra em novo round,
  mas é o candidato número 1 da triagem da revisão final.
Task 11: minor (deferred): nenhum teste exercita a limpeza do catalog.jsonl.tmp.
Task 11: minor (deferred, pré-existente): shutil.move só é atômico dentro do mesmo
  sistema de arquivos; temp do SO pode estar em outro volume.

TODAS AS 11 TASKS COMPLETAS — 96 testes. Revisão final do branch despachada.

## Revisão final do branch — veredito: merge com correções

Ruling final 1: `theatrical` congela nos filmes admitidos como acervo — o refresh
  chaveia em `track == RECENTE`, mas um lançamento grande passa de 50 votos em
  dias e entra como acervo. Corrige o predicado. Meu Ruling 2 do pré-voo dizia
  eliminar exatamente isso e chaveou errado.
Ruling final 2: catálogo passa a ser gravado ANTES da construção do site. O
  catálogo custa 40 min de API; o site é derivado e regenera em segundos. Perder
  o primeiro por causa do segundo é absurdo. `limite_index_mb` sobe para 12.0
  até a calibração real (pendência 4 do spec).
Ruling final 3: `poster_path` e `overview` entram no modelo `Movie` AGORA. Eu
  tratei como problema do plano 2 e errei: sem eles a carga inicial teria que ser
  refeita inteira. *Custo se errado:* catalog.jsonl maior.
Ruling final 4: `region: "BR"` sai das varreduras do discover. Ele interage com
  filtro de data e pode estar estreitando o catálogo em silêncio — justamente a
  cauda longa estrangeira que o motor existe pra achar. Não filtramos mais por
  streaming, e `apenas_no_cinema` lê release_dates por conta própria.
  *Custo se errado:* nenhum filtro a menos é sempre recuperável; a mais, não.
Ruling final 5: Task 11 parked (nomes.json não atômico) — REVERTIDO para conserto.
  O revisor final mostrou que a exposição é justamente o working tree local, que
  é onde o projeto vive nas próximas semanas (carga inicial e calibração manuais,
  interrompíveis com Ctrl-C). O padrão os.replace já está 20 linhas abaixo.
Ruling final 6: Task 8 parked — conclusão mantida, RACIOCÍNIO CORRIGIDO. O revisor
  final mostrou que meu argumento (suavização mantém qualidade longe de zero)
  está certo no resultado mas errado na causa: a afinidade é normalizada em
  [0,1] e a qualidade não, então a mistura real é ~91/9, não 75/25. O código
  fica; a alavanca, se um dia incomodar, é normalizar a qualidade também.
Ruling final 7: `shutil.move` entre volumes — elevado de Minor para conserto.
  Um kwarg (`mkdtemp(dir=raiz)`) elimina anulação silenciosa da atomicidade.
Demais Minors adiados: mantidos como estão, conforme triagem do revisor final.
  Duas decisões registradas de propósito: leitura de catálogo/perfil corrompido
  DEVE levantar em vez de degradar — degradar republicaria 40 mil filmes
  repontuados só por qualidade, em silêncio.
Onda de correções final: seções A, B, C commitadas (d79e51b, abd102e, 6504c4f);
  D1 commitada por mim após a interrupção (e0caabf). 107 testes.
Ruling final 8: os ids de keyword do `vibes.json` que escrevi no plano estão
  ERRADOS — o agente verificou 3 contra a API e achou "found footage"->ancient
  history, "espionagem"->mass murder, "julgamento"->kidnapping. Eu os chutei.
  Um id errado não falha: enche a fileira de filmes irrelevantes em silêncio.
  Decidido: gerar o dicionário por script que consulta /search/keyword e só
  aceita correspondência EXATA de nome, descartando o resto. Fica repetível.
  *Custo se errado:* algumas expressões a menos no dicionário.
Onda final completa: A,B,C,D commitadas (d79e51b..33b2481). 214 vibes verificadas
  contra a API, README escrito, 107 testes. Re-revisão escopada única despachada.
Re-revisão da onda final: 20/20 ADDRESSED, zero Critical/Important novos.
  Revisor confirmou que a inversão da ordem (Ruling final 2) é estritamente
  melhor: o risco saiu de "perder 40 min de rede" para "repetir alguns segundos
  de serialização local".
Adjudicação 1: `fdf-*` fora do .gitignore — corrigido pelo controller (ae57fac).
Adjudicação 2: parked — chaves do vibes.json sem acento (`vinganca`). Aparece na
  home como "Hoje a vibe é: vinganca". Ruling: cosmético e pré-existente (herdado
  das 12 entradas que escrevi no plano); nada além da exibição depende da grafia,
  confirmado pelo revisor. NÃO abre segunda onda. Fica como primeiro item de
  follow-up, decisão do Fabio.

BRANCH PRONTO: 27 commits, 107 testes, revisão final limpa.
