"""Orquestração do pipeline. Publica tudo ou não publica nada."""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import logging
import os
import shutil
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

from sync.admission import RECENTE, classificar
from sync.build import escrever_site_data
from sync.catalog import escrever_catalogo, ler_catalogo, montar_filme
from sync.config import Admissao, carregar_config
from sync.discover import descobrir_fatiado
from sync.enrich import buscar_detalhes
from sync.exports import baixar_export, ids_novos
from sync.profile import construir_gosto, ler_perfil
from sync.score import pontuar
from sync.shelves import Contexto, montar_fileiras
from sync.theatrical import apenas_no_cinema
from sync.tmdb import TMDBClient

logger = logging.getLogger(__name__)


def publicar_atomico(temporario: Path, definitivo: Path) -> None:
    """Troca o conteúdo do destino por rename-aside, sem nunca deixar o
    destino inexistente entre um passo e outro.

    rmtree seguido de move não é atômico: um crash entre os dois deixa o
    site sem catálogo nenhum — pior que servir o de ontem, que é
    exatamente o que essa função existe para evitar. Em vez disso, o
    conteúdo atual é movido para um backup ao lado, o novo conteúdo é
    movido para o lugar, e só então o backup é descartado. Cada passo é uma
    renomeação: um crash a qualquer momento deixa o destino antigo ou o
    novo no lugar — nunca nada.

    Se a rodada anterior travou entre mover o destino para o backup e mover
    o novo conteúdo para o lugar, o backup ainda está lá e o destino não
    existe — o primeiro passo desta chamada restaura o backup antes de
    seguir, para a rodada travada se autocurar em vez de ficar quebrada.
    """
    backup = definitivo.parent / f".{definitivo.name}-anterior"
    definitivo.parent.mkdir(parents=True, exist_ok=True)

    if backup.exists() and not definitivo.exists():
        shutil.move(str(backup), str(definitivo))

    if backup.exists():
        # Sobra de uma rodada anterior que travou depois do último passo;
        # descartável, pois o destino já está correto.
        shutil.rmtree(backup)

    if definitivo.exists():
        shutil.move(str(definitivo), str(backup))

    shutil.move(str(temporario), str(definitivo))

    if backup.exists():
        shutil.rmtree(backup)


async def _ids_carga_inicial(
    cliente: TMDBClient, hoje: date, cfg: Admissao
) -> set[int]:
    """Duas varreduras que juntas cobrem as regras de admissão sem puxar
    o acervo inteiro do TMDB (~900 mil filmes).

    A varredura de acervo já aplica o piso de votos no próprio /discover,
    então o ruído nunca sai do servidor. A varredura recente cobre só a
    janela de lançamentos recentes, sem piso de votos, para não perder
    filmes novos que ainda não acumularam consenso. `classificar` continua
    sendo a autoridade final — este filtro só poupa rede.
    """
    # Sem "region": no /discover ele interage com o filtro de data de
    # lançamento (presente em toda fatia via _fatiar_intervalo) e restringiria
    # silenciosamente o catálogo a filmes com lançamento no Brasil — cortando
    # exatamente a cauda longa obscura, estrangeira e antiga que essa engine
    # existe para trazer. "language" continua, porque controla só os títulos
    # devolvidos em pt-BR.
    params_base = {
        "language": "pt-BR",
        "sort_by": "popularity.desc",
    }

    acervo = await descobrir_fatiado(
        cliente,
        {**params_base, "vote_count.gte": cfg.min_votos_acervo},
        ano_final=hoje.year,
    )

    inicio_recente = hoje - timedelta(days=cfg.meses_recente * 30)
    recente = await descobrir_fatiado(
        cliente,
        params_base,
        ano_inicial=inicio_recente.year,
        ano_final=hoje.year,
    )

    return {r["id"] for r in acervo} | {r["id"] for r in recente}


async def _ids_para_processar(
    cliente: TMDBClient,
    raiz: Path,
    hoje: date,
    carga_inicial: bool,
    cfg_admissao: Admissao,
) -> tuple[set[int], set[int] | None]:
    """Devolve os ids a processar e, fora da carga inicial, o export de hoje
    — para o chamador persistir como baseline do diff de amanhã.

    A escrita de `tmdb_ids_ontem.json.gz` NÃO acontece aqui: fica a cargo de
    `executar`, dentro da seção atômica, junto com o catálogo. Escrevê-la
    aqui, antes de qualquer busca de detalhes, deixaria a baseline do diff
    apontando pra hoje mesmo que a rodada falhasse depois e o catálogo não
    fosse atualizado — a próxima rodada compararia contra a base errada e
    perderia os filmes novos daquele dia pra sempre (ver B2 no fix wave).
    """
    if carga_inicial:
        return await _ids_carga_inicial(cliente, hoje, cfg_admissao), None

    export_hoje = await baixar_export(hoje)
    caminho_ontem = raiz / "data" / "tmdb_ids_ontem.json.gz"
    if caminho_ontem.exists():
        with gzip.open(caminho_ontem, "rt", encoding="utf-8") as arquivo:
            ontem = set(json.load(arquivo))
    else:
        ontem = await baixar_export(hoje - timedelta(days=1))

    return ids_novos(export_hoje, ontem), export_hoje


def _escrever_ids_ontem(raiz: Path, ids: set[int]) -> None:
    """Grava o export de hoje, comprimido, para servir de baseline do diff
    de amanhã — nome e formato conforme o spec (`tmdb_ids_ontem.json.gz`).

    O arquivo carrega ~900 mil ids e é reescrito todo dia; sem gzip seriam
    uns 6 MB de churn diário, no repositório cujo desenho inteiro existe
    pra manter os deltas pequenos. Temp-file + os.replace: uma escrita
    torta aqui deixaria a próxima rodada comparando contra um .gz quebrado.
    """
    caminho = raiz / "data" / "tmdb_ids_ontem.json.gz"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_name(caminho.name + ".tmp")
    with gzip.open(temporario, "wt", encoding="utf-8") as arquivo:
        json.dump(sorted(ids), arquivo)
    os.replace(temporario, caminho)


def _carregar_nomes(raiz: Path) -> dict[str, dict[int, str]]:
    """Nomes de diretores e elenco aprendidos em rodadas anteriores.

    Um filme só tem seus detalhes buscados de novo quando entra no
    catálogo ou enquanto está na trilha "recente" — uma vez virado
    "acervo", nunca mais é refeito. Sem persistir os nomes, as fileiras
    "Mais de" e "Com" acabariam mostrando o id numérico da pessoa em vez do
    nome assim que o filme que a trouxe parasse de ser reprocessado.
    """
    caminho = raiz / "data" / "nomes.json"
    if not caminho.exists():
        return {"director": {}, "cast": {}}

    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    return {
        "director": {int(k): v for k, v in (bruto.get("director") or {}).items()},
        "cast": {int(k): v for k, v in (bruto.get("cast") or {}).items()},
    }


def _escrever_nomes(raiz: Path, nomes: dict[str, dict[int, str]]) -> None:
    """Grava os nomes acumulados. Nunca remove entradas — um nome correto
    uma vez continua correto, mesmo que o filme que o trouxe suma do que é
    reprocessado nesta rodada.

    Temp-file + os.replace, o mesmo padrão do catálogo: uma escrita torta
    aqui deixaria `data/nomes.json` corrompido, e como `_carregar_nomes` faz
    um `json.loads` sem guarda logo no início de `executar`, toda rodada
    seguinte morreria na primeira linha, sem nenhum caminho de autocura.
    """
    caminho = raiz / "data" / "nomes.json"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    serializavel = {
        tipo: {str(id_): nome for id_, nome in pessoas.items()}
        for tipo, pessoas in nomes.items()
    }
    temporario = caminho.with_name(caminho.name + ".tmp")
    temporario.write_text(
        json.dumps(serializavel, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temporario, caminho)


def _carregar_vibes(raiz: Path) -> dict[str, list[int]]:
    """Dicionário vibe → keywords para a fileira "Hoje a vibe é". Ausente
    não é fatal — como `ler_catalogo`, `ler_perfil` e `_carregar_nomes`,
    degrada para vazio e a rodada segue, só sem essa fileira, em vez de
    derrubar o build inteiro depois de todo o trabalho de rede já feito.
    """
    caminho = raiz / "data" / "vibes.json"
    if not caminho.exists():
        logger.warning(
            "data/vibes.json ausente — a fileira 'vibe' fica ausente nesta rodada"
        )
        return {}
    return json.loads(caminho.read_text(encoding="utf-8"))


async def executar(
    *, raiz: Path, token: str, hoje: date, carga_inicial: bool
) -> None:
    cfg = carregar_config(raiz / "config.json")
    catalogo = ler_catalogo(raiz / "data" / "catalog.jsonl")
    perfil = ler_perfil(raiz / "data" / "profile.json")
    protegidos = set(perfil.movies)
    nomes = _carregar_nomes(raiz)

    # Orçamento de retry maior que o padrão de TMDBClient: uma rodada de
    # carga inicial faz 100 mil+ requisições ao longo de 40 minutos contra
    # uma API com limite de taxa — improvável não é a palavra, é esperado
    # que algum id tropece nisso. Os defaults da classe continuam os de
    # sempre; só a chamada do pipeline pede mais paciência.
    async with TMDBClient(token, max_retries=8, backoff_base=1.0) as cliente:
        alvos, export_hoje = await _ids_para_processar(
            cliente, raiz, hoje, carga_inicial, cfg.admissao
        )
        novos = {i for i in alvos if i not in catalogo}
        # Todo filme já na trilha "recente" é reprocessado a cada rodada:
        # sem isso, `vote_count` e `theatrical` congelam no valor do dia da
        # admissão e a graduação para "acervo" nunca acontece. Um filme
        # "acervo" com `theatrical=True` também precisa entrar aqui: um
        # lançamento amplo passa de 50 votos em poucos dias e é admitido
        # como acervo antes mesmo de `classificar` olhar pra janela de
        # lançamento — sem reprocessar, ele fica preso na fileira "Nos
        # cinemas" para sempre, mesmo depois do lançamento digital sair.
        recentes_existentes = {
            i
            for i, f in catalogo.items()
            if f.track == RECENTE or f.theatrical
        }
        ids_para_buscar = novos | recentes_existentes
        detalhes, removidos = await buscar_detalhes(cliente, ids_para_buscar)

    if removidos:
        logger.warning(
            "removidos do catálogo por não existirem mais no TMDB (404/410): %s",
            sorted(removidos),
        )
    for id_removido in removidos:
        # Sai do catálogo, mas o registro em profile.json não é tocado — o
        # histórico do Fabio vira um "órfão", como o spec pede.
        catalogo.pop(id_removido, None)

    for detalhe in detalhes:
        id_ = detalhe["id"]
        trilha = classificar(detalhe, hoje, cfg.admissao)
        if trilha is None:
            # Um filme já catalogado que deixou de se qualificar (janela do
            # "recente" passou sem votos suficientes) é removido — a menos
            # que o Fabio já o tenha avaliado, caso em que o histórico dele
            # nunca pode ser destruído por uma decisão do pipeline.
            if id_ in catalogo and id_ not in protegidos:
                del catalogo[id_]
            continue

        # Preserva a data de entrada original ao reprocessar um filme já
        # catalogado — do contrário todo refresh pareceria uma novidade e
        # inundaria a fileira "entrou hoje no catálogo".
        added = catalogo[id_].added if id_ in catalogo else hoje.isoformat()

        filme = montar_filme(
            detalhe,
            track=trilha,
            theatrical=apenas_no_cinema(detalhe.get("release_dates") or {}, hoje),
            added=added,
        )
        catalogo[filme.id] = filme

        creditos = detalhe.get("credits") or {}
        for pessoa in creditos.get("crew") or []:
            if pessoa.get("job") == "Director":
                nomes["director"][pessoa["id"]] = pessoa.get("name", "")
        for pessoa in (creditos.get("cast") or [])[:5]:
            nomes["cast"][pessoa["id"]] = pessoa.get("name", "")

    gosto = construir_gosto(perfil, catalogo, k=cfg.motor.suavizacao_k)
    pontuacao = pontuar(catalogo, gosto, cfg.motor)

    vibes = _carregar_vibes(raiz)
    fileiras = montar_fileiras(
        Contexto(
            catalogo=catalogo, perfil=perfil, pontuacao=pontuacao, gosto=gosto,
            hoje=hoje, cfg=cfg, vibes=vibes, nomes=nomes,
        )
    )

    caminho_catalogo = raiz / "data" / "catalog.jsonl"
    temporario_catalogo = caminho_catalogo.with_name(caminho_catalogo.name + ".tmp")
    temporario_site: Path | None = None
    try:
        # O catálogo é publicado PRIMEIRO, antes do site. Ele é o artefato
        # caro — até 40 minutos de chamadas ao TMDB numa carga inicial — e a
        # fonte de verdade; site/data/ é inteiramente derivado dele e
        # reconstrói em segundos. Se `escrever_site_data` falhar (por
        # exemplo por estourar `limite_index_mb`), a rodada perde só a
        # etapa barata: o catálogo já está salvo, e a próxima rodada
        # reconstrói o site sem refazer nenhuma chamada de rede. A ordem
        # antiga fazia o oposto — arriscava jogar fora 40 minutos de fetch
        # pela etapa mais barata do pipeline, exatamente ao contrário do
        # que a atomicidade deveria proteger.
        #
        # Grava o catálogo por um arquivo temporário ao lado do definitivo;
        # escrever_catalogo continua fazendo a serialização, só não é mais
        # ela quem decide o caminho final. os.replace é uma renomeação
        # atômica tanto no Windows quanto no POSIX.
        escrever_catalogo(temporario_catalogo, catalogo.values())
        os.replace(temporario_catalogo, caminho_catalogo)

        # data/nomes.json e data/tmdb_ids_ontem.json.gz entram na mesma
        # seção "nada mais pode falhar de forma perigosa" do catálogo — os
        # três, cada um por temp-file + os.replace. Escrevê-los antes desse
        # ponto (como o código fazia) deixava um estado inconsistente
        # possível: uma rodada que falhasse depois avançaria a baseline do
        # diff ou os nomes aprendidos sem o catálogo em disco refletir isso,
        # e a rodada seguinte compararia contra a base errada.
        _escrever_nomes(raiz, nomes)
        if export_hoje is not None:
            _escrever_ids_ontem(raiz, export_hoje)

        # dir=raiz: o diretório temporário do site precisa estar no mesmo
        # sistema de arquivos que o destino (raiz/site/data). Sem isso,
        # `tempfile.mkdtemp` cairia no temp global do SO — que pode estar em
        # outro volume — e o `shutil.move` dentro de `publicar_atomico`
        # degradaria de rename para copy+delete, anulando a garantia de
        # atomicidade que essa função existe pra dar.
        temporario_site = Path(tempfile.mkdtemp(prefix="fdf-", dir=raiz))

        # Só agora o site é construído e publicado — derivado do catálogo
        # que acabou de ser gravado, já em segurança em disco.
        escrever_site_data(temporario_site, catalogo, pontuacao, fileiras, cfg.build)
        publicar_atomico(temporario_site, raiz / "site" / "data")
    finally:
        # Um diretório temporário órfão a cada falha, num job diário
        # agendado, vira lixo acumulado sem limite — limpo em todo caminho,
        # sucesso ou falha.
        if temporario_site is not None and temporario_site.exists():
            shutil.rmtree(temporario_site, ignore_errors=True)
        if temporario_catalogo.exists():
            temporario_catalogo.unlink(missing_ok=True)


def main() -> None:
    # INFO no stderr: uma carga inicial roda ~40 minutos sem interação, e
    # sem log não há como distinguir trabalho de travamento.
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(prog="sync")
    parser.add_argument(
        "--carga-inicial",
        action="store_true",
        help="varre o discover inteiro em vez de usar o export diário",
    )
    parser.add_argument("--raiz", type=Path, default=Path("."))
    args = parser.parse_args()

    token = os.environ.get("TMDB_TOKEN")
    if not token:
        sys.exit("TMDB_TOKEN não está definido no ambiente")

    asyncio.run(
        executar(
            raiz=args.raiz,
            token=token,
            hoje=date.today(),
            carga_inicial=args.carga_inicial,
        )
    )


if __name__ == "__main__":
    main()
