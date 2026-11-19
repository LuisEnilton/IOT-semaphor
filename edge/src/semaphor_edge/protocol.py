"""Contrato MQTT (ver docs/mqtt-topics.md)."""

import json

ROADS = ("N", "L", "S", "O")
STATES = ("red", "yellow", "green", "off", "flash_yellow")


def topic(intersection_id: str, kind: str) -> str:
    return f"semaphor/{intersection_id}/{kind}"


def build_cmd(roads: dict[str, str]) -> str:
    for road, state in roads.items():
        if road not in ROADS:
            raise ValueError(f"via inválida: {road!r} (use {ROADS})")
        if state not in STATES:
            raise ValueError(f"estado inválido: {state!r} (use {STATES})")
    return json.dumps({"roads": roads})
