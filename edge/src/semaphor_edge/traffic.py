"""Contagem de veículos por via (E2).

- VehicleCounter: interface que o algoritmo de fila usa. A visão computacional (E4)
  vai implementar a mesma interface.
- SimulatedTraffic: tráfego simulado. Veículos chegam aleatoriamente em cada via e
  saem durante o verde. Também mede o tempo de espera (métrica D3).
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field
from typing import Protocol

from .protocol import ROADS

# Cenário padrão: via A (N/S) mais carregada que a via B (L/O). Veículos por segundo.
DEFAULT_ARRIVALS = {"N": 0.35, "S": 0.3, "L": 0.1, "O": 0.1}


class VehicleCounter(Protocol):
    def counts(self) -> dict[str, int]:
        """Veículos parados em cada via (`N`, `L`, `S`, `O`)."""
        ...


def parse_arrivals(text: str) -> dict[str, float]:
    """Converte 'N=0.3,S=0.3,L=0.1,O=0.1' em taxas de chegada (veículos/s)."""
    rates = dict.fromkeys(ROADS, 0.0)
    for part in filter(None, (p.strip() for p in text.split(","))):
        road, _, value = part.partition("=")
        road = road.strip().upper()
        if road not in ROADS:
            raise ValueError(f"via inválida em --chegadas: {road!r} (use {ROADS})")
        try:
            rate = float(value)
        except ValueError:
            raise ValueError(f"taxa inválida para {road}: {value!r}") from None
        if rate < 0:
            raise ValueError(f"taxa negativa para {road}")
        rates[road] = rate
    return rates


@dataclass
class TrafficStats:
    served: int = 0
    total_wait_s: float = 0.0
    max_queue: dict[str, int] = field(default_factory=lambda: dict.fromkeys(ROADS, 0))
    # Espera dos veículos que ainda estavam na fila ao fim da medição.
    pending: int = 0
    pending_wait_s: float = 0.0

    @property
    def avg_wait_s(self) -> float:
        """Tempo médio de espera, contando também quem ainda está na fila."""
        n = self.served + self.pending
        return (self.total_wait_s + self.pending_wait_s) / n if n else 0.0


class SimulatedTraffic:
    """Filas simuladas por via.

    Chegadas: processo aleatório com taxa `arrivals[via]` (veículos/s).
    Saídas: com a via em verde, sai um veículo a cada `headway_s` segundos.
    """

    def __init__(
        self,
        arrivals: dict[str, float] | None = None,
        headway_s: float = 1.0,
        seed: int | None = None,
    ) -> None:
        self.arrivals = {r: (arrivals or DEFAULT_ARRIVALS).get(r, 0.0) for r in ROADS}
        self.headway_s = headway_s
        self._rng = random.Random(seed)
        self._queues: dict[str, deque[float]] = {r: deque() for r in ROADS}
        self._credit = dict.fromkeys(ROADS, 0.0)
        self._last: float | None = None
        self.stats = TrafficStats()

    def counts(self) -> dict[str, int]:
        return {r: len(q) for r, q in self._queues.items()}

    def update(self, now: float, roads: dict[str, str]) -> None:
        """Avança a simulação até `now` com o estado atual do semáforo."""
        if self._last is None:
            self._last = now
            return
        dt = now - self._last
        self._last = now
        if dt <= 0:
            return
        for road, queue in self._queues.items():
            # Chegadas: em média `rate * dt` veículos neste intervalo.
            expected = self.arrivals[road] * dt
            arrivals = int(expected) + (self._rng.random() < expected - int(expected))
            queue.extend([now] * arrivals)
            # Saídas durante o verde.
            if roads.get(road) == "green":
                self._credit[road] += dt / self.headway_s
                while self._credit[road] >= 1 and queue:
                    self._credit[road] -= 1
                    self.stats.served += 1
                    self.stats.total_wait_s += now - queue.popleft()
                if not queue:
                    self._credit[road] = 0.0  # não acumula vazão com a via vazia
            else:
                self._credit[road] = 0.0
            self.stats.max_queue[road] = max(self.stats.max_queue[road], len(queue))

    def finish(self, now: float) -> TrafficStats:
        """Fecha a medição incluindo a espera de quem ainda está na fila."""
        self.stats.pending = sum(len(q) for q in self._queues.values())
        self.stats.pending_wait_s = sum(now - t for q in self._queues.values() for t in q)
        return self.stats
