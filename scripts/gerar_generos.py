"""Gera data/generos.json a partir da lista oficial de generos do TMDB.

Executado uma vez, manualmente. Nao faz parte do pipeline diario -- a lista
de generos do TMDB e pequena (~19 itens) e praticamente nunca muda.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

RAIZ = Path(__file__).resolve().parent.parent


def buscar_generos(token: str) -> dict[str, str]:
    resposta = httpx.get(
        "https://api.themoviedb.org/3/genre/movie/list",
        params={"language": "pt-BR"},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )
    resposta.raise_for_status()
    dados = resposta.json()
    return {str(g["id"]): g["name"] for g in dados["genres"]}


def main() -> None:
    token = os.environ.get("TMDB_TOKEN")
    if not token:
        sys.exit("TMDB_TOKEN nao esta definido no ambiente")

    generos = buscar_generos(token)
    destino = RAIZ / "data" / "generos.json"
    destino.write_text(
        json.dumps(generos, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    print(f"{len(generos)} generos escritos em {destino}")


if __name__ == "__main__":
    main()
