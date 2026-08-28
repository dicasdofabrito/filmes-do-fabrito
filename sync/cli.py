"""Orquestração do pipeline. Publica tudo ou não publica nada."""

from __future__ import annotations

import argparse
import asyncio
import json
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


def publicar_atomico(temporario: Path, definitivo: Path) -> None:
    """Troca o conteúdo do destino de uma vez.

    Um catálogo pela metade é pior que um catálogo de ontem, então a
    publicação só acontece depois que tudo foi gerado com sucesso.
    """
    definitivo.parent.mkdir(parents=True, exist_ok=True)
    if definitivo.exists():
        shutil.rmtree(definitivo)
    shutil.move(str(temporario), str(definitivo))


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
    params_base = {
        "language": "pt-BR",
        "region": "BR",
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


async def executar(
    *, raiz: Path, token: str, hoje: date, carga_inicial: bool
) -> None:
    cfg = carregar_config(raiz / "config.json")
    catalogo = ler_catalogo(raiz / "data" / "catalog.jsonl")
    perfil = ler_perfil(raiz / "data" / "profile.json")
    protegidos = set(perfil.movies)

    async with TMDBClient(token) as cliente:
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
        detalhes = await buscar_detalhes(cliente, ids_para_buscar)

    nomes: dict[str, dict[int, str]] = {"director": {}, "cast": {}}

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

    vibes = json.loads((raiz / "data" / "vibes.json").read_text(encoding="utf-8"))
    fileiras = montar_fileiras(
        Contexto(
            catalogo=catalogo, perfil=perfil, pontuacao=pontuacao, gosto=gosto,
            hoje=hoje, cfg=cfg, vibes=vibes, nomes=nomes,
        )
    )

    temporario = Path(tempfile.mkdtemp(prefix="fdf-"))
    escrever_site_data(temporario, catalogo, pontuacao, fileiras, cfg.build)
    escrever_catalogo(raiz / "data" / "catalog.jsonl", catalogo.values())
    publicar_atomico(temporario, raiz / "site" / "data")


def main() -> None:
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
