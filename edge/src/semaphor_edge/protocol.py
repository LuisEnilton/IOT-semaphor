"""Contrato MQTT (ver docs/mqtt-topics.md)."""

import json

ROADS = ("N", "L", "S", "O")
STATES = ("red", "yellow", "green", "off", "flash_yellow")

# Vias que abrem juntas: A = N + S (semáforos S1 e S3), B = L + O (S2 e S4).
ROAD_GROUP = {"N": "A", "S": "A", "L": "B", "O": "B"}
ACTIVE_STATES = ("green", "yellow")


def topic(intersection_id: str, kind: str) -> str:
    return f"semaphor/{intersection_id}/{kind}"


def has_conflict(roads: dict[str, str]) -> bool:
    """True se vias A e B estão em verde/amarelo ao mesmo tempo."""
    active = {ROAD_GROUP[r] for r, s in roads.items() if s in ACTIVE_STATES}
    return len(active) > 1


def build_cmd(roads: dict[str, str]) -> str:
    for road, state in roads.items():
        if road not in ROADS:
            raise ValueError(f"via inválida: {road!r} (use {ROADS})")
        if state not in STATES:
            raise ValueError(f"estado inválido: {state!r} (use {STATES})")
    if has_conflict(roads):
        raise ValueError("conflito: vias A (N/S) e B (L/O) em verde/amarelo ao mesmo tempo")
    return json.dumps({"roads": roads})
