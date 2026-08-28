"""Leitura tipada do config.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Admissao:
    min_votos_acervo: int
    meses_recente: int
    min_votos_recente: int
    min_popularidade_recente: float
    min_duracao: int


@dataclass(frozen=True)
class Motor:
    suavizacao_k: float
    qualidade_m: int
    peso_afinidade: float
    min_avaliacoes: int
    pesos: dict[str, float]


@dataclass(frozen=True)
class Build:
    limite_index_mb: float
    tamanho_fileira: int


@dataclass(frozen=True)
class Config:
    admissao: Admissao
    motor: Motor
    build: Build
    fileiras: tuple[str, ...]


def carregar_config(caminho: Path) -> Config:
    bruto = json.loads(caminho.read_text(encoding="utf-8"))
    return Config(
        admissao=Admissao(**bruto["admissao"]),
        motor=Motor(**bruto["motor"]),
        build=Build(**bruto["build"]),
        fileiras=tuple(bruto["fileiras"]),
    )
