"""Simulação offline (E3.3): compara o ciclo fixo com o algoritmo de fila.

Roda em tempo simulado (sem MQTT e sem esperar), com o mesmo PhaseController usado no
Pi, e mede o tempo médio de espera por veículo (métrica D3).
"""

from __future__ import annotations

from dataclasses import dataclass

from .phases import PhaseController, Timing
from .policy import QueueParams, QueuePolicy
from .traffic import SimulatedTraffic, TrafficStats


def simulate(
    arrivals: dict[str, float],
    duration_s: float,
    timing: Timing,
    adaptive: bool,
    params: QueueParams | None = None,
    seed: int = 0,
    dt: float = 0.1,
) -> TrafficStats:
    params = params or QueueParams()
    traffic = SimulatedTraffic(arrivals, headway_s=params.sec_per_vehicle, seed=seed)
    policy = QueuePolicy(traffic, params).green_for if adaptive else None
    green_policy = (lambda g: policy(traffic.counts(), g)) if policy else None
    ctrl = PhaseController(0.0, timing, green_policy)
    traffic.update(0.0, ctrl.roads)
    steps = int(duration_s / dt)
    t = 0.0
    for i in range(1, steps + 1):
        t = i * dt
        traffic.update(t, ctrl.roads)
        ctrl.update(t)
    return traffic.finish(t)


@dataclass
class Summary:
    name: str
    avg_wait_s: float
    max_queue: int
    served: int


def compare(
    arrivals: dict[str, float],
    duration_s: float,
    timing: Timing,
    params: QueueParams | None = None,
    seeds: int = 5,
) -> list[Summary]:
    """Média de `seeds` rodadas (mesmas chegadas para os dois métodos)."""
    results = []
    for name, adaptive in (("ciclo fixo", False), ("fila (adaptativo)", True)):
        runs = [simulate(arrivals, duration_s, timing, adaptive, params, s) for s in range(seeds)]
        results.append(
            Summary(
                name,
                sum(r.avg_wait_s for r in runs) / seeds,
                max(max(r.max_queue.values()) for r in runs),
                round(sum(r.served for r in runs) / seeds),
            )
        )
    return results
