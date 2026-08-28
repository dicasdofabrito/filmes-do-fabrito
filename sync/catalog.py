"""Modelo do filme e persistência do catálogo em JSONL."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

MAX_ELENCO = 5


@dataclass(frozen=True)
class Movie:
    id: int
    title: str
    year: int | None
    runtime: int
    genres: tuple[int, ...]
    keywords: tuple[int, ...]
    vote_average: float
    vote_count: int
    directors: tuple[int, ...]
    cast: tuple[int, ...]
    language: str
    track: str
    theatrical: bool
    added: str

    def to_row(self) -> dict:
        """Serializa com chaves curtas — o arquivo tem dezenas de milhares
        de linhas e cada byte de nome de campo é multiplicado por isso."""
        return {
            "id": self.id,
            "t": self.title,
            "y": self.year,
            "r": self.runtime,
            "g": list(self.genres),
            "k": list(self.keywords),
            "v": self.vote_average,
            "n": self.vote_count,
            "d": list(self.directors),
            "c": list(self.cast),
            "l": self.language,
            "st": self.track,
            "th": self.theatrical,
            "a": self.added,
        }

    @classmethod
    def from_row(cls, row: dict) -> Movie:
        return cls(
            id=row["id"],
            title=row["t"],
            year=row["y"],
            runtime=row["r"],
            genres=tuple(row["g"]),
            keywords=tuple(row["k"]),
            vote_average=row["v"],
            vote_count=row["n"],
            directors=tuple(row["d"]),
            cast=tuple(row["c"]),
            language=row["l"],
            track=row["st"],
            theatrical=row["th"],
            # `catalog.jsonl` é dado de projeto com vida longa versionado no
            # git; um arquivo gravado antes deste campo existir não pode
            # virar ilegível — degrada para string vazia.
            added=row.get("a", ""),
        )


def montar_filme(
    detalhe: dict, *, track: str, theatrical: bool, added: str
) -> Movie:
    """Converte a resposta de /movie/{id} com append_to_response no modelo."""
    creditos = detalhe.get("credits") or {}
    equipe = creditos.get("crew") or []
    elenco = creditos.get("cast") or []
    palavras = (detalhe.get("keywords") or {}).get("keywords") or []
    lancamento = detalhe.get("release_date") or ""

    return Movie(
        id=detalhe["id"],
        title=detalhe.get("title") or detalhe.get("original_title") or "",
        year=int(lancamento[:4]) if lancamento[:4].isdigit() else None,
        runtime=detalhe.get("runtime") or 0,
        genres=tuple(g["id"] for g in detalhe.get("genres") or []),
        keywords=tuple(p["id"] for p in palavras),
        vote_average=detalhe.get("vote_average") or 0.0,
        vote_count=detalhe.get("vote_count") or 0,
        directors=tuple(p["id"] for p in equipe if p.get("job") == "Director"),
        cast=tuple(p["id"] for p in elenco[:MAX_ELENCO]),
        language=detalhe.get("original_language") or "",
        track=track,
        theatrical=theatrical,
        added=added,
    )


def ler_catalogo(caminho: Path) -> dict[int, Movie]:
    if not caminho.exists():
        return {}

    filmes: dict[int, Movie] = {}
    with caminho.open(encoding="utf-8") as arquivo:
        for linha in arquivo:
            if linha.strip():
                filme = Movie.from_row(json.loads(linha))
                filmes[filme.id] = filme
    return filmes


def escrever_catalogo(caminho: Path, filmes: Iterable[Movie]) -> None:
    """Grava ordenado por id. A ordem estável é o que permite ao git
    guardar apenas o delta diário em vez do arquivo inteiro."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8", newline="\n") as arquivo:
        for filme in sorted(filmes, key=lambda f: f.id):
            arquivo.write(json.dumps(filme.to_row(), ensure_ascii=False) + "\n")
