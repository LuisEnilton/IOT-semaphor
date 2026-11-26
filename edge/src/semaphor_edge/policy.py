"""Algoritmo de fila (E3): decide quanto tempo de verde cada via recebe.

Regra: ao abrir o verde de um grupo (A = N+S, B = L+O), dá tempo para escoar a maior
fila do grupo (fila × segundos por veículo), limitado entre `min_green_s` e `max_green_s`.

Anti-inanição (E3.2): as fases continuam alternando A e B (ver phases.py), então
nenhuma via fica mais que max_green_s + amarelo + vermelho geral sem verde, mesmo
que a contagem diga que ela está vazia (ex.: falha da câmera).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .protocol import ROAD_GROUP
from .traffic import VehicleCounter

log = logging.getLogger("semaphor_edge")


@dataclass(frozen=True)
class QueueParams:
    min_green_s: float = 3.0
    max_green_s: float = 15.0
    sec_per_vehicle: float = 1.0  # tempo para um veículo cruzar (vazão de saturação)

    def __post_init__(self) -> None:
        if not 0 < self.min_green_s <= self.max_green_s:
            raise ValueError("é preciso 0 < verde mínimo <= verde máximo")
        if self.sec_per_vehicle <= 0:
            raise ValueError("segundos por veículo deve ser maior que zero")


class QueuePolicy:
    """GreenPolicy baseada na fila (ver phases.GreenPolicy)."""

    def __init__(self, counter: VehicleCounter, params: QueueParams | None = None) -> None:
        self.counter = counter
        self.params = params or QueueParams()

    def green_for(self, counts: dict[str, int], group: str) -> float:
        queue = max((n for road, n in counts.items() if ROAD_GROUP.get(road) == group), default=0)
        p = self.params
        return min(p.max_green_s, max(p.min_green_s, queue * p.sec_per_vehicle))

    def __call__(self, group: str) -> float:
        counts = self.counter.counts()
        green = self.green_for(counts, group)
        filas = " ".join(f"{r}={counts[r]}" for r, g in ROAD_GROUP.items() if g == group)
        log.info("verde %s: fila %s -> %.1f s", group, filas, green)
        return green
