"""Regras de entrada no catálogo, em duas trilhas."""

from __future__ import annotations

from datetime import date

from sync.config import Admissao

ACERVO = "acervo"
RECENTE = "recente"


def _data_de(detalhe: dict) -> date | None:
    bruto = detalhe.get("release_date") or ""
    try:
        return date.fromisoformat(bruto)
    except ValueError:
        return None


def classificar(detalhe: dict, hoje: date, cfg: Admissao) -> str | None:
    """Decide a trilha de admissão de um filme, ou None se ele não entra."""
    if detalhe.get("adult"):
        return None

    if (detalhe.get("runtime") or 0) < cfg.min_duracao:
        return None

    # Consenso acumulado tem prioridade: um lançamento que já explodiu de
    # votos entra como acervo e não expira depois de 18 meses.
    if detalhe.get("vote_count", 0) >= cfg.min_votos_acervo:
        return ACERVO

    lancamento = _data_de(detalhe)
    if lancamento is None:
        return None

    dias_de_vida = (hoje - lancamento).days
    if not 0 <= dias_de_vida <= cfg.meses_recente * 30:
        return None

    tem_votos = detalhe.get("vote_count", 0) >= cfg.min_votos_recente
    tem_tracao = detalhe.get("popularity", 0.0) >= cfg.min_popularidade_recente
    return RECENTE if (tem_votos or tem_tracao) else None
