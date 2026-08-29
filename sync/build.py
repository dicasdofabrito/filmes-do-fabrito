"""Escrita dos artefatos consumidos pelo site."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from sync.catalog import Movie
from sync.config import Build
from sync.score import Scoring
from sync.shelves import Shelf

BYTES_POR_MB = 1024 * 1024


class IndiceGrandeDemais(RuntimeError):
    """O índice passou do limite configurado e degradaria o carregamento."""


def _escrever(caminho: Path, dados: object) -> int:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
    caminho.write_text(texto, encoding="utf-8")
    return len(texto.encode("utf-8"))


def calcular_offsets(caminho: Path) -> dict[int, tuple[int, int]]:
    """Lê catalog.jsonl e devolve, por id, o intervalo de bytes [inicio,
    fim] (fim inclusive) da linha daquele filme -- o mesmo intervalo que um
    header `Range: bytes=inicio-fim` HTTP busca. Cada linha é
    `json.dumps(row) + "\n"`; o offset é medido nos bytes UTF-8 do arquivo,
    não em caracteres, porque é isso que o servidor conta para o Range.
    """
    offsets: dict[int, tuple[int, int]] = {}
    posicao = 0
    with caminho.open("rb") as arquivo:
        for linha_bytes in arquivo:
            linha = json.loads(linha_bytes.decode("utf-8"))
            inicio = posicao
            fim = posicao + len(linha_bytes) - 1
            offsets[linha["id"]] = (inicio, fim)
            posicao += len(linha_bytes)
    return offsets


def escrever_site_data(
    destino: Path,
    catalogo: dict[int, Movie],
    pontuacao: Scoring,
    fileiras: list[Shelf],
    cfg: Build,
) -> None:
    ordenados = sorted(
        catalogo.values(),
        key=lambda f: pontuacao.scores.get(f.id, 0.0),
        reverse=True,
    )

    indice = {
        "movies": [
            {
                "id": f.id,
                "t": f.title,
                "y": f.year,
                "r": f.runtime,
                "g": list(f.genres),
                "k": list(f.keywords),
                "s": round(pontuacao.scores.get(f.id, 0.0), 4),
                # "n": vote_count — o onboarding de partida a frio precisa
                # dos 200 filmes de maior vote_count, e o site não pode
                # calcular isso sem esse número estar publicado.
                "n": f.vote_count,
                # "th": theatrical — a fileira "Nos cinemas" filtra por ele.
                "th": f.theatrical,
                "p": f.poster_path,
                "d": list(f.directors),
                "c": list(f.cast),
                "l": f.language,
            }
            for f in ordenados
        ]
    }
    tamanho = _escrever(destino / "index.json", indice)

    limite = cfg.limite_index_mb * BYTES_POR_MB
    if tamanho > limite:
        raise IndiceGrandeDemais(
            f"index.json tem {tamanho / BYTES_POR_MB:.2f} MB, "
            f"acima do limite de {cfg.limite_index_mb} MB"
        )

    _escrever(
        destino / "shelves.json",
        {
            "shelves": [
                {"key": s.key, "title": s.title, "ids": list(s.movie_ids)}
                for s in fileiras
            ]
        },
    )

    invertido: dict[int, list[int]] = defaultdict(list)
    for filme in catalogo.values():
        for keyword in filme.keywords:
            invertido[keyword].append(filme.id)

    _escrever(
        destino / "keywords.json",
        {str(k): sorted(v) for k, v in sorted(invertido.items())},
    )

    caminho_catalogo = destino.parent / "data" / "catalog.jsonl"
    offsets = calcular_offsets(caminho_catalogo)
    _escrever(
        destino / "offsets.json",
        {str(id_): [inicio, fim] for id_, (inicio, fim) in sorted(offsets.items())},
    )
