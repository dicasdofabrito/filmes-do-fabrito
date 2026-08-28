import gzip
import json
from datetime import date

import httpx
import respx

from sync.exports import baixar_export, ids_novos, url_export


def test_url_export_usa_o_formato_mes_dia_ano():
    assert url_export(date(2026, 8, 27)) == (
        "http://files.tmdb.org/p/exports/movie_ids_08_27_2026.json.gz"
    )


@respx.mock
async def test_baixar_export_le_jsonl_comprimido():
    linhas = b"\n".join(
        json.dumps({"id": i, "original_title": f"F{i}"}).encode() for i in (1, 2, 3)
    )
    respx.get(url_export(date(2026, 8, 27))).mock(
        return_value=httpx.Response(200, content=gzip.compress(linhas))
    )

    assert await baixar_export(date(2026, 8, 27)) == {1, 2, 3}


def test_ids_novos_devolve_apenas_a_diferenca():
    assert ids_novos({1, 2, 3}, {1, 2}) == {3}
    assert ids_novos({1}, {1, 2}) == set()
