"""Perfil de avaliações e construção do vetor de gosto."""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from sync.catalog import Movie


@dataclass(frozen=True)
class Entry:
    seen: bool = False
    rating: int | None = None
    want: bool = False
    at: str = ""


@dataclass(frozen=True)
class Profile:
    movies: dict[int, Entry] = field(default_factory=dict)

    def liked_ids(self) -> set[int]:
        return {i for i, e in self.movies.items() if e.rating == 1}

    def disliked_ids(self) -> set[int]:
        return {i for i, e in self.movies.items() if e.rating == -1}

    def seen_ids(self) -> set[int]:
        return {i for i, e in self.movies.items() if e.seen}

    def wanted_ids(self) -> set[int]:
        return {i for i, e in self.movies.items() if e.want}


def ler_perfil(caminho: Path) -> Profile:
    if not caminho.exists():
        return Profile()

    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    return Profile(
        movies={
            int(id_): Entry(
                seen=dados.get("seen", False),
                rating=dados.get("rating"),
                want=dados.get("want", False),
                at=dados.get("at", ""),
            )
            for id_, dados in (bruto.get("movies") or {}).items()
        }
    )


def features_of(filme: Movie) -> dict[str, tuple]:
    """Decompõe um filme no saco de características que o motor compara."""
    return {
        "keyword": filme.keywords,
        "director": filme.directors,
        "cast": filme.cast,
        "genre": filme.genres,
        "decade": ((filme.year // 10) * 10,) if filme.year else (),
        "language": (filme.language,) if filme.language else (),
    }


@dataclass(frozen=True)
class Taste:
    weights: dict[tuple[str, object], float]
    n_ratings: int


def _frequencia_no_catalogo(catalogo: dict[int, Movie]) -> Counter:
    frequencia: Counter = Counter()
    for filme in catalogo.values():
        for tipo, valores in features_of(filme).items():
            for valor in set(valores):
                frequencia[(tipo, valor)] += 1
    return frequencia


def _pesar(
    curtidos: list[Movie],
    rejeitados: list[Movie],
    catalogo: dict[int, Movie],
    k: float,
) -> dict[tuple[str, object], float]:
    frequencia = _frequencia_no_catalogo(catalogo)
    total = max(len(catalogo), 1)

    positivos: Counter = Counter()
    negativos: Counter = Counter()
    for filme in curtidos:
        for tipo, valores in features_of(filme).items():
            for valor in set(valores):
                positivos[(tipo, valor)] += 1
    for filme in rejeitados:
        for tipo, valores in features_of(filme).items():
            for valor in set(valores):
                negativos[(tipo, valor)] += 1

    pesos: dict[tuple[str, object], float] = {}
    for caracteristica in set(positivos) | set(negativos):
        p = positivos[caracteristica]
        n = negativos[caracteristica]
        # Suavização bayesiana: uma única observação não vira convicção.
        afinidade = (p - n) / (p + n + k)
        # Normalização por raridade: o que é comum não discrimina.
        idf = math.log(total / (1 + frequencia.get(caracteristica, 0)))
        pesos[caracteristica] = afinidade * idf

    return pesos


def construir_gosto(
    perfil: Profile, catalogo: dict[int, Movie], *, k: float = 2.0
) -> Taste:
    curtidos = [catalogo[i] for i in perfil.liked_ids() if i in catalogo]
    rejeitados = [catalogo[i] for i in perfil.disliked_ids() if i in catalogo]
    return Taste(
        weights=_pesar(curtidos, rejeitados, catalogo, k),
        n_ratings=len(curtidos) + len(rejeitados),
    )


def gosto_de_um_filme(
    filme: Movie, catalogo: dict[int, Movie], *, k: float = 2.0
) -> Taste:
    """Vetor de gosto derivado de um único filme, para 'o que se parece
    com esse'."""
    return Taste(weights=_pesar([filme], [], catalogo, k), n_ratings=1)
