"""Montagem das fileiras da home."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date

from sync.catalog import Movie
from sync.config import Config
from sync.profile import Profile, Taste, features_of, gosto_de_um_filme
from sync.score import Scoring, afinidade

ANOS_PARA_CLASSICO = 25
DURACAO_CURTA = 100
MIN_FILMES_PARA_DIMENSAO = 200
LINGUAS_LOCAIS = frozenset({"en", "pt", "es"})
IDADE_MINIMA_ANTIGO = 40


@dataclass(frozen=True)
class Shelf:
    key: str
    title: str
    movie_ids: tuple[int, ...]


@dataclass(frozen=True)
class Contexto:
    catalogo: dict[int, Movie]
    perfil: Profile
    pontuacao: Scoring
    gosto: Taste
    hoje: date
    cfg: Config
    vibes: dict[str, list[int]]
    nomes: dict[str, dict[int, str]]


def _ordenar(ctx: Contexto, ids) -> tuple[int, ...]:
    limite = ctx.cfg.build.tamanho_fileira
    return tuple(
        sorted(ids, key=lambda i: ctx.pontuacao.scores.get(i, 0.0), reverse=True)
    )[:limite]


def _nao_vistos(ctx: Contexto) -> set[int]:
    return set(ctx.catalogo) - ctx.perfil.seen_ids()


def _estrangeiro(filme: Movie) -> bool:
    return filme.language not in LINGUAS_LOCAIS


def _antigo(ctx: Contexto, filme: Movie) -> bool:
    return filme.year is not None and ctx.hoje.year - filme.year > IDADE_MINIMA_ANTIGO


def _elegiveis_para_descoberta(ctx: Contexto) -> set[int]:
    """Filmes não vistos que podem aparecer nas fileiras de descoberta
    "normais". Estrangeiros e filmes com mais de 40 anos saem daqui -- só
    aparecem em "Filmes estrangeiros"/"Filmes antigos". A watchlist é a
    única fileira que NÃO usa isso: o que o Fabio marcou como "quero ver"
    aparece lá mesmo sendo estrangeiro ou antigo, porque foi escolha dele,
    não uma recomendação automática do sistema."""
    return {
        i
        for i in _nao_vistos(ctx)
        if not _estrangeiro(ctx.catalogo[i]) and not _antigo(ctx, ctx.catalogo[i])
    }


def _percentil(valores: list[float], fracao: float) -> float:
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    indice = min(int(len(ordenados) * fracao), len(ordenados) - 1)
    return ordenados[indice]


def _melhor_do_tipo(ctx: Contexto, tipo: str) -> object | None:
    candidatos = {
        valor: peso
        for (t, valor), peso in ctx.gosto.weights.items()
        if t == tipo and peso > 0
    }
    return max(candidatos, key=candidatos.get) if candidatos else None


# --- as treze fileiras ------------------------------------------------------


def _watchlist(ctx: Contexto) -> tuple[str, tuple[int, ...]]:
    ids = ctx.perfil.wanted_ids() & set(ctx.catalogo)
    return "Você marcou pra ver", _ordenar(ctx, ids)


def _novos(ctx: Contexto) -> tuple[str, tuple[int, ...]]:
    hoje = ctx.hoje.isoformat()
    elegiveis = _elegiveis_para_descoberta(ctx)
    ids = {i for i, f in ctx.catalogo.items() if f.added == hoje} & elegiveis
    return "Entrou hoje no catálogo", _ordenar(ctx, ids)


def _similar(ctx: Contexto) -> tuple[str, tuple[int, ...]]:
    curtidos = [
        (ctx.perfil.movies[i].at, i)
        for i in ctx.perfil.liked_ids()
        if i in ctx.catalogo
    ]
    if not curtidos:
        return "", ()

    _, referencia = max(curtidos)
    filme = ctx.catalogo[referencia]
    gosto = gosto_de_um_filme(filme, ctx.catalogo)

    candidatos = _elegiveis_para_descoberta(ctx) - {referencia}
    if not candidatos:
        return f"Porque você gostou de {filme.title}", ()

    afinidades = {
        i: afinidade(ctx.catalogo[i], gosto, ctx.cfg.motor.pesos) for i in candidatos
    }

    # Mesma maquinaria do motor principal (`pontuar`): afinidade
    # normalizada por min-max combinada com a âncora de qualidade, no
    # mesmo split de `peso_afinidade` — não só afinidade crua. Sem a
    # âncora, a fileira enchia de filmes obscuros que só compartilham
    # keyword com a referência, sem nenhum piso de qualidade.
    peso = ctx.cfg.motor.peso_afinidade
    menor, maior = min(afinidades.values()), max(afinidades.values())
    amplitude = maior - menor

    if amplitude < 1e-12:
        # Amplitude zero: sem informação de afinidade pra discriminar,
        # volta pra qualidade pura — mesma degradação de `pontuar`.
        scores = {i: ctx.pontuacao.qualities.get(i, 0.0) for i in candidatos}
    else:
        scores = {
            i: peso * ((afinidades[i] - menor) / amplitude)
            + (1 - peso) * ctx.pontuacao.qualities.get(i, 0.0)
            for i in candidatos
        }

    melhores = sorted(scores, key=scores.get, reverse=True)
    limite = ctx.cfg.build.tamanho_fileira
    return f"Porque você gostou de {filme.title}", tuple(melhores[:limite])


def _vibe(ctx: Contexto) -> tuple[str, tuple[int, ...]]:
    if not ctx.vibes:
        return "", ()

    # Semente na data: a vibe é sorteada, mas estável ao longo do dia.
    nomes = sorted(ctx.vibes)
    escolhida = nomes[ctx.hoje.toordinal() % len(nomes)]
    alvo = set(ctx.vibes[escolhida])

    ids = {
        i
        for i in _elegiveis_para_descoberta(ctx)
        if alvo & set(ctx.catalogo[i].keywords)
    }
    return f"Hoje a vibe é: {escolhida}", _ordenar(ctx, ids)


def _por_pessoa(ctx: Contexto, tipo: str, rotulo: str) -> tuple[str, tuple[int, ...]]:
    pessoa = _melhor_do_tipo(ctx, tipo)
    if pessoa is None:
        return "", ()

    ids = {
        i
        for i in _elegiveis_para_descoberta(ctx)
        if pessoa in features_of(ctx.catalogo[i])[tipo]
    }
    nome = ctx.nomes.get(tipo, {}).get(pessoa, str(pessoa))
    return f"{rotulo} {nome}", _ordenar(ctx, ids)


def _diretor(ctx: Contexto) -> tuple[str, tuple[int, ...]]:
    return _por_pessoa(ctx, "director", "Mais de")


def _ator(ctx: Contexto) -> tuple[str, tuple[int, ...]]:
    return _por_pessoa(ctx, "cast", "Com")


def _curto(ctx: Contexto) -> tuple[str, tuple[int, ...]]:
    ids = {i for i in _elegiveis_para_descoberta(ctx) if ctx.catalogo[i].runtime < DURACAO_CURTA}
    return "Cabe antes de dormir", _ordenar(ctx, ids)


def _classicos(ctx: Contexto) -> tuple[str, tuple[int, ...]]:
    limite_ano = ctx.hoje.year - ANOS_PARA_CLASSICO

    elegiveis = {
        i
        for i, filme in ctx.catalogo.items()
        if filme.year is not None
        and filme.year <= limite_ano
        and i not in ctx.perfil.movies
        and not _estrangeiro(filme)
        and not _antigo(ctx, filme)
    }
    # Corte calculado sobre a própria população elegível: usar a distribuição
    # do catálogo inteiro (incluindo vistos) faria o corte fugir do alcance à
    # medida que os melhores filmes fossem assistidos.
    corte = _percentil(
        [ctx.pontuacao.qualities.get(i, 0.0) for i in elegiveis], 0.98
    )

    ids = {i for i in elegiveis if ctx.pontuacao.qualities.get(i, 0.0) >= corte}
    return "Clássicos que você nunca viu", _ordenar(ctx, ids)


def _aposta(ctx: Contexto) -> tuple[str, tuple[int, ...]]:
    candidatos = _elegiveis_para_descoberta(ctx)
    if not candidatos:
        return "", ()

    afins = [ctx.pontuacao.affinities.get(i, 0.0) for i in candidatos]
    piso = _percentil(afins, 0.40)
    teto = _percentil(afins, 0.70)
    # Corte de qualidade sobre a própria população não vista, pelo mesmo
    # motivo do corte em _classicos.
    corte_qualidade = _percentil(
        [ctx.pontuacao.qualities.get(i, 0.0) for i in candidatos], 0.95
    )

    ids = {
        i
        for i in candidatos
        if piso <= ctx.pontuacao.affinities.get(i, 0.0) <= teto
        and ctx.pontuacao.qualities.get(i, 0.0) >= corte_qualidade
    }
    return "Aposta arriscada", _ordenar(ctx, ids)


def _ponto_cego(ctx: Contexto) -> tuple[str, tuple[int, ...]]:
    """A dimensão de menor razão entre presença nos curtidos e presença no
    catálogo — o antídoto contra a bolha que o motor cria sozinho."""
    curtidos = [ctx.catalogo[i] for i in ctx.perfil.liked_ids() if i in ctx.catalogo]
    if not curtidos:
        return "", ()

    no_catalogo: Counter = Counter()
    for filme in ctx.catalogo.values():
        for tipo in ("genre", "language", "decade"):
            for valor in set(features_of(filme)[tipo]):
                no_catalogo[(tipo, valor)] += 1

    nos_curtidos: Counter = Counter()
    for filme in curtidos:
        for tipo in ("genre", "language", "decade"):
            for valor in set(features_of(filme)[tipo]):
                nos_curtidos[(tipo, valor)] += 1

    elegiveis = {
        chave: nos_curtidos[chave] / total
        for chave, total in no_catalogo.items()
        if total >= MIN_FILMES_PARA_DIMENSAO
    }
    if not elegiveis:
        return "", ()

    alvo = min(elegiveis, key=elegiveis.get)
    tipo, valor = alvo

    candidatos = {
        i
        for i in _elegiveis_para_descoberta(ctx)
        if valor in features_of(ctx.catalogo[i])[tipo]
    }
    # Corte de qualidade sobre a própria população elegível para a dimensão
    # escolhida — as estatísticas de seleção da dimensão continuam sobre o
    # catálogo inteiro (correto), só o corte de qualidade muda.
    corte = _percentil(
        [ctx.pontuacao.qualities.get(i, 0.0) for i in candidatos], 0.98
    )

    ids = {i for i in candidatos if ctx.pontuacao.qualities.get(i, 0.0) >= corte}
    return "Ponto cego", _ordenar(ctx, ids)


def _cinemas(ctx: Contexto) -> tuple[str, tuple[int, ...]]:
    ids = {
        i
        for i, filme in ctx.catalogo.items()
        if filme.theatrical and not _estrangeiro(filme) and not _antigo(ctx, filme)
    }
    return "Nos cinemas", _ordenar(ctx, ids)


def _estrangeiros(ctx: Contexto) -> tuple[str, tuple[int, ...]]:
    ids = {i for i in _nao_vistos(ctx) if _estrangeiro(ctx.catalogo[i])}
    return "Filmes estrangeiros", _ordenar(ctx, ids)


def _antigos(ctx: Contexto) -> tuple[str, tuple[int, ...]]:
    # Exclui os que também são estrangeiros -- idioma tem prioridade sobre
    # idade quando os dois se aplicam ao mesmo filme (ver _elegiveis_para_
    # descoberta); senão um filme velho E estrangeiro apareceria nas duas
    # fileiras ao mesmo tempo.
    ids = {
        i
        for i in _nao_vistos(ctx)
        if _antigo(ctx, ctx.catalogo[i]) and not _estrangeiro(ctx.catalogo[i])
    }
    return "Filmes antigos", _ordenar(ctx, ids)


GERADORES = {
    "watchlist": _watchlist,
    "novos": _novos,
    "similar": _similar,
    "vibe": _vibe,
    "diretor": _diretor,
    "ator": _ator,
    "curto": _curto,
    "classicos": _classicos,
    "aposta": _aposta,
    "ponto_cego": _ponto_cego,
    "estrangeiros": _estrangeiros,
    "antigos": _antigos,
    "cinemas": _cinemas,
}


def montar_fileiras(ctx: Contexto) -> list[Shelf]:
    """Monta as fileiras na ordem do config, omitindo as que ficaram vazias."""
    fileiras: list[Shelf] = []

    for chave in ctx.cfg.fileiras:
        gerador = GERADORES.get(chave)
        if gerador is None:
            continue
        titulo, ids = gerador(ctx)
        if ids:
            fileiras.append(Shelf(key=chave, title=titulo, movie_ids=ids))

    return fileiras
