"""Busca em lote dos detalhes completos de filmes."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Iterable

from sync.tmdb import TMDBClient, TMDBError

logger = logging.getLogger(__name__)

CAMPOS_EXTRAS = "keywords,credits,release_dates"

# A cada quantos fetches concluídos um log de progresso é emitido. Numa carga
# inicial de 40 minutos e 100 mil+ ids, sem isso não há como distinguir
# trabalho de travamento.
INTERVALO_LOG = 500

# 404 (nao encontrado) e 410 (removido) significam que o filme deixou de
# existir no TMDB — fusao de duplicatas, remocao de conteudo. Isso nao e
# uma falha do build: e um fato sobre o catalogo, tratado a parte.
STATUS_FILME_REMOVIDO = {404, 410}

_PADRAO_STATUS = re.compile(r"^(\d{3}) em ")


def _status_de(erro: TMDBError) -> int | None:
    """Extrai o status HTTP de um TMDBError definitivo, quando presente.

    TMDBClient nao expoe o status como atributo estruturado, so no texto da
    mensagem ("{status} em {path}: ..."). Erros que nao vem dessa origem
    (ex.: "esgotadas N tentativas em ...") nao casam e devolvem None.
    """
    casamento = _PADRAO_STATUS.match(str(erro))
    return int(casamento.group(1)) if casamento else None


async def buscar_detalhes(
    cliente: TMDBClient, ids: Iterable[int], *, concorrencia: int = 16
) -> tuple[list[dict], set[int]]:
    """Busca /movie/{id} com tudo que o motor precisa, em paralelo limitado.

    Keywords, duração, elenco e diretor não vêm no /discover — só aqui.

    Devolve os detalhes obtidos e o conjunto de ids que o TMDB reportou como
    removidos (404/410) — esses não derrubam a busca, só saem do resultado e
    são reportados ao chamador para saírem do catálogo. Qualquer outro erro
    continua definitivo e propaga, abortando a busca inteira.
    """
    ids = tuple(ids)
    total = len(ids)
    limitador = asyncio.Semaphore(concorrencia)
    removidos: set[int] = set()
    concluidos = 0

    async def um(id_: int) -> dict | None:
        nonlocal concluidos
        async with limitador:
            try:
                return await cliente.get(
                    f"/movie/{id_}",
                    append_to_response=CAMPOS_EXTRAS,
                    language="pt-BR",
                )
            except TMDBError as erro:
                if _status_de(erro) in STATUS_FILME_REMOVIDO:
                    removidos.add(id_)
                    return None
                raise
            finally:
                # Incremento é seguro sem lock: asyncio é cooperativo e não
                # há `await` entre a leitura e a escrita de `concluidos`.
                concluidos += 1
                if concluidos % INTERVALO_LOG == 0:
                    logger.info("detalhes buscados: %d/%d", concluidos, total)

    resultados = await asyncio.gather(*(um(i) for i in ids))
    detalhes = [r for r in resultados if r is not None]
    return detalhes, removidos
