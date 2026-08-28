"""Motor de pontuação: afinidade com o gosto mais âncora de qualidade."""

from __future__ import annotations

from dataclasses import dataclass

from sync.catalog import Movie
from sync.config import Motor
from sync.profile import Taste, features_of

NOTA_MAXIMA = 10.0


def afinidade(filme: Movie, gosto: Taste, pesos: dict[str, float]) -> float:
    """Média dos pesos das características do filme, ponderada por tipo.

    Tipos ausentes têm seu peso redistribuído proporcionalmente entre os
    presentes. Sem isso, um filme sem keywords perderia 40% do score por
    uma lacuna do TMDB, e não por discordância de gosto — penalizando
    sistematicamente os filmes obscuros.
    """
    presentes: dict[str, float] = {}

    for tipo, valores in features_of(filme).items():
        unicos = set(valores)
        if not unicos:
            continue
        soma = sum(gosto.weights.get((tipo, v), 0.0) for v in unicos)
        presentes[tipo] = soma / len(unicos)

    if not presentes:
        return 0.0

    total = sum(pesos.get(tipo, 0.0) for tipo in presentes)
    if total == 0.0:
        return 0.0

    return sum(
        pesos.get(tipo, 0.0) / total * valor for tipo, valor in presentes.items()
    )


def qualidade_bayesiana(
    media: float, votos: int, *, m: int, media_global: float
) -> float:
    """Puxa notas apoiadas em poucos votos na direção da média global.

    Impede que um filme com nota 9,8 e 51 votos vença um consolidado.
    """
    return (votos / (votos + m)) * media + (m / (votos + m)) * media_global


@dataclass(frozen=True)
class Scoring:
    scores: dict[int, float]
    affinities: dict[int, float]
    qualities: dict[int, float]


def pontuar(catalogo: dict[int, Movie], gosto: Taste, cfg: Motor) -> Scoring:
    if not catalogo:
        return Scoring(scores={}, affinities={}, qualities={})

    # Só filmes com voto registrado entram na média global. Filmes "recente"
    # admitidos por popularidade têm `vote_average = 0.0` — incluí-los
    # puxaria a âncora bayesiana pra baixo e penalizaria sistematicamente
    # todo filme de poucos votos, o oposto do que `qualidade_bayesiana`
    # existe para fazer.
    com_votos = [f.vote_average for f in catalogo.values() if f.vote_count > 0]
    if com_votos:
        media_global = sum(com_votos) / len(com_votos)
    else:
        media_global = sum(f.vote_average for f in catalogo.values()) / len(catalogo)

    qualidades = {
        id_: qualidade_bayesiana(
            filme.vote_average,
            filme.vote_count,
            m=cfg.qualidade_m,
            media_global=media_global,
        )
        / NOTA_MAXIMA
        for id_, filme in catalogo.items()
    }
    afinidades = {
        id_: afinidade(filme, gosto, cfg.pesos) for id_, filme in catalogo.items()
    }

    # Partida a frio: sem avaliações suficientes não há sinal utilizável,
    # então o ranking cai para qualidade pura.
    if gosto.n_ratings < cfg.min_avaliacoes:
        return Scoring(
            scores=dict(qualidades), affinities=afinidades, qualities=qualidades
        )

    menor = min(afinidades.values())
    maior = max(afinidades.values())
    amplitude = maior - menor

    # Amplitude zero: sem informação de afinidade, volta para qualidade pura.
    # Isso protege contra dois problemas: (1) quando a amplitude é exatamente zero
    # (todos os filmes têm mesma afinidade), o score não deve ser comprimido para
    # 25% da qualidade; (2) flutuações de ponto flutuante podem produzir uma
    # amplitude minúscula que dividiria valores para fora de [0, 1].
    if amplitude < 1e-12:
        return Scoring(
            scores=dict(qualidades), affinities=afinidades, qualities=qualidades
        )

    scores = {
        id_: cfg.peso_afinidade * ((afinidades[id_] - menor) / amplitude)
        + (1 - cfg.peso_afinidade) * qualidades[id_]
        for id_ in catalogo
    }
    return Scoring(scores=scores, affinities=afinidades, qualities=qualidades)
