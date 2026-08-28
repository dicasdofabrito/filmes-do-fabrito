"""Gera `data/vibes.json` verificando cada id de keyword contra a API do TMDB.

Ferramenta de desenvolvimento, avulsa — não faz parte do pipeline (`sync/`)
nem da suíte de testes, e é a única coisa neste repositório que fala com a
API do TMDB fora de `sync/tmdb.py`.

Por quê. As keywords do TMDB são em inglês; o dono da ferramenta digita em
português. Este script resolve cada expressão em português contra um ou mais
termos candidatos em inglês, aceitando um termo somente quando ele bate
exatamente (sem diferenciar maiúscula/minúscula) com o `name` de uma keyword
retornada pela busca — um id nunca é aceito por aproximação, porque um id
levemente errado não falha: ele silenciosamente preenche a fileira de vibe
com filmes que não têm nada a ver com a expressão pedida.

Uso:
    export TMDB_TOKEN=...        # nunca commitar este valor
    python scripts/gerar_vibes.py

O token é lido só do ambiente e nunca é escrito em nenhum arquivo nem
impresso no terminal.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# Permite rodar o script tanto com `python scripts/gerar_vibes.py` (cwd na
# raiz do repo) quanto de qualquer outro diretório, sem depender de o pacote
# `sync` já estar instalado em modo editável.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sync.tmdb import TMDBClient  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
DESTINO = RAIZ / "data" / "vibes.json"

# Concorrência limitada para não estourar o limite de taxa do TMDB — o
# TMDBClient já reexecuta 429s, mas é mais rápido não provocá-los.
MAX_CONCORRENCIA = 5

# Expressão em português → termos candidatos em inglês a buscar em
# /search/keyword. Cada termo é uma aposta; só entra no arquivo final o id
# de um termo que bateu exatamente com o nome de uma keyword do TMDB. Uma
# expressão com vários termos pode resolver para vários ids (ex.: "fim do
# mundo" cobre tanto "post-apocalyptic future" quanto "apocalypse").
CANDIDATOS: dict[str, list[str]] = {
    # --- sentimentos e estados de espírito ---
    "melancolia": ["melancholy"],
    "esperanca": ["hope"],
    "tensao": ["suspense", "tension"],
    "nostalgia": ["nostalgia"],
    "solidao": ["loneliness", "solitude"],
    "raiva": ["anger", "rage"],
    "medo": ["fear"],
    "alegria": ["joy", "happiness"],
    "tristeza": ["sadness"],
    "ciume": ["jealousy"],
    "culpa": ["guilt"],
    "redencao": ["redemption"],
    "obsessao": ["obsession"],
    "paranoia": ["paranoia"],
    "angustia": ["anguish", "anxiety"],
    "coragem": ["courage", "bravery"],
    "desespero": ["despair", "desperation"],
    "euforia": ["euphoria"],
    "vergonha": ["shame"],
    "traicao": ["betrayal"],
    "ambicao": ["ambition"],
    "inveja": ["envy"],
    "arrependimento": ["regret"],
    "humilhacao": ["humiliation"],
    "solidariedade": ["solidarity"],
    "resiliencia": ["resilience"],
    "esperanca ingenua": ["naivety", "innocence"],
    "loucura": ["madness", "insanity"],
    "vazio existencial": ["existentialism"],

    # --- ambientações ---
    "deserto": ["desert"],
    "espaco": ["outer space", "space"],
    "submarino": ["submarine"],
    "prisao": ["prison"],
    "floresta": ["forest"],
    "selva": ["jungle"],
    "ilha deserta": ["desert island"],
    "ilha": ["island"],
    "pantano": ["swamp"],
    "montanha": ["mountain"],
    "oceano": ["ocean"],
    "alto mar": ["high seas"],
    "metropole": ["metropolis"],
    "suburbio": ["suburb", "suburbia"],
    "fazenda": ["farm"],
    "castelo": ["castle"],
    "mansao": ["mansion"],
    "hospital": ["hospital"],
    "hospital psiquiatrico": ["psychiatric hospital", "mental institution"],
    "trem": ["train"],
    "navio": ["ship"],
    "aviao": ["airplane"],
    "bunker": ["bunker"],
    "circo": ["circus"],
    "cassino": ["casino"],
    "colegio": ["high school"],
    "universidade": ["college", "university"],
    "acampamento de ferias": ["summer camp"],
    "artico": ["arctic"],
    "antartida": ["antarctica"],
    "vulcao": ["volcano"],
    "caverna": ["cave"],
    "labirinto": ["labyrinth", "maze"],
    "estrada": ["road trip", "road"],
    "bairro pobre": ["ghetto", "slum"],
    "zona rural": ["rural life", "countryside"],

    # --- formas de enredo ---
    "assalto": ["heist"],
    "vinganca": ["revenge"],
    "fuga": ["escape"],
    "julgamento": ["trial"],
    "sequestro": ["kidnapping"],
    "perseguicao": ["chase"],
    "investigacao criminal": ["criminal investigation", "investigation"],
    "assassinato": ["murder"],
    "assassino em serie": ["serial killer"],
    "roubo": ["robbery", "theft"],
    "golpe de estado": ["coup d'etat", "coup"],
    "conspiracao": ["conspiracy"],
    "rebeliao": ["rebellion"],
    "revolucao": ["revolution"],
    "resgate": ["rescue"],
    "fuga da prisao": ["prison escape"],
    "caca ao tesouro": ["treasure hunt"],
    "infiltracao": ["undercover"],
    "traicao amorosa": ["infidelity"],
    "triangulo amoroso": ["love triangle"],
    "amor proibido": ["forbidden love"],
    "primeiro amor": ["first love"],
    "amizade improvavel": ["unlikely friendship"],
    "rivalidade": ["rivalry"],
    "competicao": ["competition"],
    "torneio": ["tournament"],
    "corrida": ["race"],
    "jogo mortal": ["deadly game"],
    "sobrevivencia em grupo": ["survival"],
    "duplo agente": ["double agent"],
    "agente disfarcado": ["undercover cop"],
    "cacada humana": ["manhunt"],

    # --- épocas e temas ---
    "guerra fria": ["cold war"],
    "segunda guerra mundial": ["world war ii"],
    "primeira guerra mundial": ["world war i"],
    "guerra do vietna": ["vietnam war"],
    "guerra civil": ["civil war"],
    "holocausto": ["holocaust"],
    "mafia": ["mafia"],
    "crime organizado": ["organized crime"],
    "gangster": ["gangster"],
    "faroeste": ["western"],
    "cowboy": ["cowboy"],
    "samurai": ["samurai"],
    "ninja": ["ninja"],
    "pirata": ["pirate"],
    "viking": ["viking"],
    "idade media": ["middle ages"],
    "roma antiga": ["ancient rome"],
    "grecia antiga": ["ancient greece"],
    "egito antigo": ["ancient egypt"],
    "mitologia grega": ["greek mythology"],
    "mitologia nordica": ["norse mythology"],
    "viagem no tempo": ["time travel"],
    "inteligencia artificial": ["artificial intelligence"],
    "realidade virtual": ["virtual reality"],
    "clonagem": ["cloning"],
    "experimento genetico": ["genetic engineering"],
    "vida aliegena": ["extraterrestrial life"],
    "invasao alienigena": ["alien invasion"],
    "primeiro contato": ["first contact"],
    "viagem espacial": ["space travel"],
    "corrida espacial": ["space race"],
    "exploracao espacial": ["space exploration"],
    "ditadura": ["dictatorship"],
    "terrorismo": ["terrorism"],
    "espionagem": ["espionage"],
    "guerra nuclear": ["nuclear war"],
    "apocalipse zumbi": ["zombie"],
    "vampiro": ["vampire"],
    "lobisomem": ["werewolf"],
    "fantasma": ["ghost"],
    "casa mal-assombrada": ["haunted house"],
    "bruxaria": ["witch", "witchcraft"],
    "conto de fadas": ["fairy tale"],
    "super-heroi": ["superhero"],
    "vigilante": ["vigilante"],
    "robo": ["robot"],
    "ciborgue": ["cyborg"],
    "android": ["android"],
    "dinossauro": ["dinosaur"],
    "tubarao": ["shark"],
    "colonialismo": ["colonialism"],
    "escravidao": ["slavery"],
    "apartheid": ["apartheid"],
    "racismo": ["racism"],
    "direitos civis": ["civil rights"],
    "pandemia": ["pandemic"],
    "surto de virus": ["virus outbreak", "epidemic"],
    "peste": ["plague"],
    "terremoto": ["earthquake"],
    "tsunami": ["tsunami"],
    "furacao": ["hurricane"],
    "inundacao": ["flood"],
    "acidente de aviao": ["plane crash"],
    "naufragio": ["shipwreck"],
    "civilizacao perdida": ["lost civilization"],
    "gladiador": ["gladiator"],
    "cavaleiro medieval": ["knight"],
    "familia real": ["royal family", "monarchy"],
    "sequestro de refem": ["hostage"],
    "bomba relogio": ["bomb"],
    "arma nuclear": ["nuclear weapon"],
    "ufologia": ["ufo"],
    "loop temporal": ["time loop"],
    "universo paralelo": ["parallel universe"],
    "realidade alternativa": ["alternate reality"],
    "multiverso": ["multiverse"],
    "utopia": ["utopia"],

    # --- ja existentes no arquivo anterior, mantidos e reverificados ---
    "fim do mundo": ["post-apocalyptic future", "apocalypse", "dystopia"],
    "found footage": ["found footage"],
    "distopia": ["dystopia"],
    "monstro gigante": ["kaiju", "giant monster"],
    "isolamento": ["isolation"],

    # --- situações de vida ---
    "luto": ["grief"],
    "paternidade": ["fatherhood"],
    "maternidade": ["motherhood"],
    "amizade": ["friendship"],
    "exilio": ["exile"],
    "imigracao": ["immigration"],
    "refugiados": ["refugee"],
    "adocao": ["adoption"],
    "divorcio": ["divorce"],
    "casamento": ["wedding"],
    "gravidez na adolescencia": ["teenage pregnancy"],
    "crise de meia-idade": ["midlife crisis"],
    "envelhecimento": ["aging"],
    "demencia": ["dementia"],
    "doenca terminal": ["terminal illness"],
    "cancer": ["cancer"],
    "dependencia quimica": ["drug addiction"],
    "alcoolismo": ["alcoholism"],
    "suicidio": ["suicide"],
    "amadurecimento": ["coming of age"],
    "orfao": ["orphan"],
    "viuvez": ["widow"],
    "desemprego": ["unemployment"],
    "pobreza": ["poverty"],
    "heranca": ["inheritance"],
    "segredo de familia": ["family secret"],
    "familia disfuncional": ["dysfunctional family"],
    "reencontro familiar": ["family reunion"],
    "amizade na infancia": ["childhood friendship"],
    "sobrevivencia": ["survival"],
    "boxe": ["boxing"],
    "artes marciais": ["martial arts"],
    "musica e banda": ["rock band", "musician"],
    "danca": ["dance"],
    "surdocegueira": ["deafness"],
    "cegueira": ["blindness"],
    "deficiencia fisica": ["disability"],
    "doenca mental": ["mental illness"],
    "hackers": ["hacker", "hacking"],
    "vigilancia em massa": ["surveillance"],
    "corrupcao politica": ["corruption", "political corruption"],
}


async def resolver_termo(
    cliente: TMDBClient, cache: dict[str, int | None], termo: str
) -> int | None:
    """Retorna o id da keyword cujo `name` bate exatamente (sem diferenciar
    maiúscula/minúscula) com `termo`, ou None se nenhuma bater.

    Resultados são cacheados por termo (não por expressão em português),
    já que vários termos candidatos se repetem entre expressões diferentes
    e cada chamada extra é uma chamada a mais na API de outra pessoa.
    """
    chave = termo.strip().lower()
    if chave in cache:
        return cache[chave]

    resposta = await cliente.get("/search/keyword", query=termo)
    alvo = termo.strip().lower()
    id_encontrado: int | None = None
    for resultado in resposta.get("results", []):
        if str(resultado.get("name", "")).strip().lower() == alvo:
            id_encontrado = int(resultado["id"])
            break

    cache[chave] = id_encontrado
    return id_encontrado


async def resolver_expressao(
    cliente: TMDBClient,
    cache: dict[str, int | None],
    semaforo: asyncio.Semaphore,
    termos: list[str],
) -> list[int]:
    ids: list[int] = []
    for termo in termos:
        async with semaforo:
            id_encontrado = await resolver_termo(cliente, cache, termo)
        if id_encontrado is not None and id_encontrado not in ids:
            ids.append(id_encontrado)
    return ids


async def gerar() -> dict[str, list[int]]:
    token = os.environ.get("TMDB_TOKEN")
    if not token:
        sys.exit("TMDB_TOKEN não está definido no ambiente")

    resultado: dict[str, list[int]] = {}
    descartadas: list[str] = []
    cache: dict[str, int | None] = {}
    semaforo = asyncio.Semaphore(MAX_CONCORRENCIA)

    async with TMDBClient(token) as cliente:
        expressoes = list(CANDIDATOS.items())
        tarefas = [
            resolver_expressao(cliente, cache, semaforo, termos)
            for _, termos in expressoes
        ]
        listas_de_ids = await asyncio.gather(*tarefas)

    for (expressao, _termos), ids in zip(expressoes, listas_de_ids):
        if ids:
            resultado[expressao] = ids
        else:
            descartadas.append(expressao)

    if descartadas:
        print(
            f"Descartadas ({len(descartadas)}) — nenhum termo candidato "
            "bateu exatamente com uma keyword do TMDB:",
            file=sys.stderr,
        )
        for expressao in descartadas:
            print(f"  - {expressao}: {CANDIDATOS[expressao]}", file=sys.stderr)

    return dict(sorted(resultado.items()))


def main() -> None:
    vibes = asyncio.run(gerar())

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(
        json.dumps(vibes, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(
        f"\n{len(vibes)} expressões resolvidas de {len(CANDIDATOS)} "
        f"candidatas -> {DESTINO}"
    )


if __name__ == "__main__":
    main()
