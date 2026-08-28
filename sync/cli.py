"""Orquestração do pipeline. Publica tudo ou não publica nada."""

from __future__ import annotations

import argparse
import asyncio
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
) -> set[int]:
    if carga_inicial:
        return await _ids_carga_inicial(cliente, hoje, cfg_admissao)

    export_hoje = await baixar_export(hoje)
    caminho_ontem = raiz / "data" / "tmdb_ids_ontem.json"
    if caminho_ontem.exists():
        ontem = set(json.loads(caminho_ontem.read_text(encoding="utf-8")))
    else:
        ontem = await baixar_export(hoje - timedelta(days=1))

    caminho_ontem.parent.mkdir(parents=True, exist_ok=True)
    caminho_ontem.write_text(json.dumps(sorted(export_hoje)), encoding="utf-8")
    return ids_novos(export_hoje, ontem)


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
    reprocessado nesta rodada."""
    caminho = raiz / "data" / "nomes.json"
    caminho.parent.mkdir(parents=True, exist_ok=True)
    serializavel = {
        tipo: {str(id_): nome for id_, nome in pessoas.items()}
        for tipo, pessoas in nomes.items()
    }
    caminho.write_text(
        json.dumps(serializavel, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


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
        alvos = await _ids_para_processar(
            cliente, raiz, hoje, carga_inicial, cfg.admissao
        )
        novos = {i for i in alvos if i not in catalogo}
        # Todo filme já na trilha "recente" é reprocessado a cada rodada:
        # sem isso, `vote_count` e `theatrical` congelam no valor do dia da
        # admissão e a graduação para "acervo" nunca acontece.
        recentes_existentes = {
            i for i, f in catalogo.items() if f.track == RECENTE
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

    _escrever_nomes(raiz, nomes)

    gosto = construir_gosto(perfil, catalogo, k=cfg.motor.suavizacao_k)
    pontuacao = pontuar(catalogo, gosto, cfg.motor)

    vibes = json.loads((raiz / "data" / "vibes.json").read_text(encoding="utf-8"))
    fileiras = montar_fileiras(
        Contexto(
            catalogo=catalogo, perfil=perfil, pontuacao=pontuacao, gosto=gosto,
            hoje=hoje, cfg=cfg, vibes=vibes, nomes=nomes,
        )
    )

    temporario_site = Path(tempfile.mkdtemp(prefix="fdf-"))
    caminho_catalogo = raiz / "data" / "catalog.jsonl"
    temporario_catalogo = caminho_catalogo.with_name(caminho_catalogo.name + ".tmp")
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

        # Só agora o site é construído e publicado — derivado do catálogo
        # que acabou de ser gravado, já em segurança em disco.
        escrever_site_data(temporario_site, catalogo, pontuacao, fileiras, cfg.build)
        publicar_atomico(temporario_site, raiz / "site" / "data")
    finally:
        # Um diretório temporário órfão a cada falha, num job diário
        # agendado, vira lixo acumulado sem limite — limpo em todo caminho,
        # sucesso ou falha.
        if temporario_site.exists():
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
