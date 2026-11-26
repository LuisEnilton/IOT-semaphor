"""Controlador de fases do cruzamento (lógica pura, sem MQTT nem relógio real).

Ciclo: A verde -> A amarelo -> vermelho geral -> B verde -> B amarelo -> vermelho geral -> ...
Via A = N + S, via B = L + O (ver protocol.ROAD_GROUP). O tempo é sempre passado de fora
(`now`, em segundos), o que torna a lógica testável sem `time.sleep`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from .protocol import ACTIVE_STATES, ROAD_GROUP


@dataclass(frozen=True)
class Timing:
    """Durações das fases, em segundos (padrão = ciclo local do firmware)."""

    green_s: float = 5.0
    yellow_s: float = 2.0
    all_red_s: float = 1.0

    def __post_init__(self) -> None:
        for name in ("green_s", "yellow_s", "all_red_s"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} deve ser maior que zero")


class Phase(Enum):
    A_GREEN = 0
    A_YELLOW = 1
    RED_AFTER_A = 2
    B_GREEN = 3
    B_YELLOW = 4
    RED_AFTER_B = 5

    @property
    def next(self) -> Phase:
        return Phase((self.value + 1) % len(Phase))


# Estado de cada grupo em cada fase: (via A, via B).
_GROUP_STATES = {
    Phase.A_GREEN: ("green", "red"),
    Phase.A_YELLOW: ("yellow", "red"),
    Phase.RED_AFTER_A: ("red", "red"),
    Phase.B_GREEN: ("red", "green"),
    Phase.B_YELLOW: ("red", "yellow"),
    Phase.RED_AFTER_B: ("red", "red"),
}

# Recebe o grupo ("A" ou "B") ao entrar no verde e devolve a duração do verde em segundos.
# É o ponto de encaixe do algoritmo de fila (E3); o padrão usa Timing.green_s.
GreenPolicy = Callable[[str], float]


def roads_for(phase: Phase) -> dict[str, str]:
    """Estado das 4 vias numa fase, no formato do comando MQTT."""
    a, b = _GROUP_STATES[phase]
    return {road: a if group == "A" else b for road, group in ROAD_GROUP.items()}


def start_phase_for(roads: dict[str, str] | None) -> Phase:
    """Fase segura para assumir o controle a partir do estado atual do ESP32.

    Se uma via está aberta (verde/amarelo), começa pelo amarelo dela, para nunca
    cortar um verde direto para o vermelho. Sem estado conhecido, começa no vermelho geral.
    """
    active = {
        ROAD_GROUP[r] for r, s in (roads or {}).items() if r in ROAD_GROUP and s in ACTIVE_STATES
    }
    if active == {"A"}:
        return Phase.A_YELLOW
    if active == {"B"}:
        return Phase.B_YELLOW
    return Phase.RED_AFTER_B


class PhaseController:
    def __init__(
        self,
        now: float,
        timing: Timing | None = None,
        green_policy: GreenPolicy | None = None,
        start: Phase = Phase.RED_AFTER_B,
    ) -> None:
        self.timing = timing or Timing()
        self._green_policy = green_policy or (lambda _group: self.timing.green_s)
        self._enter(start, now)

    def _duration_for(self, phase: Phase) -> float:
        if phase in (Phase.A_GREEN, Phase.B_GREEN):
            green = self._green_policy("A" if phase is Phase.A_GREEN else "B")
            if green <= 0:
                raise ValueError(f"duração de verde inválida: {green}")
            return green
        if phase in (Phase.A_YELLOW, Phase.B_YELLOW):
            return self.timing.yellow_s
        return self.timing.all_red_s

    def _enter(self, phase: Phase, now: float) -> None:
        self.phase = phase
        self.phase_start = now
        self.phase_duration = self._duration_for(phase)

    def update(self, now: float) -> bool:
        """Avança no máximo uma fase. Retorna True se a fase mudou.

        Avançar uma fase por chamada garante que nenhum amarelo ou vermelho geral é pulado,
        mesmo se o loop atrasar.
        """
        if now - self.phase_start < self.phase_duration:
            return False
        self._enter(self.phase.next, now)
        return True

    @property
    def roads(self) -> dict[str, str]:
        return roads_for(self.phase)
