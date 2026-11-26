"""Contagem de veículos por via (regras puras, sem câmera nem MQTT).

A visão computacional (vision.py) entrega caixas detectadas; aqui elas viram fila por via usando
polígonos (ROIs) desenhados sobre a imagem da câmera.
"""

import json
import random
import statistics
from collections import deque
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Protocol

from .protocol import ROADS

Point = tuple[float, float]
Polygon = list[Point]
Box = tuple[float, float, float, float]  # x1, y1, x2, y2 em pixels


class VehicleCounter(Protocol):
    def counts(self) -> dict[str, int]:
        """Veículos esperando em cada via (chaves = ROADS)."""
        ...


def point_in_polygon(p: Point, poly: Polygon) -> bool:
    """Ray casting: conta quantas arestas um raio horizontal a partir de p cruza."""
    x, y = p
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def anchor(box: Box) -> Point:
    """Centro da base da caixa: é o ponto onde o veículo toca a pista."""
    x1, _y1, x2, y2 = box
    return ((x1 + x2) / 2, y2)


def count_by_roi(boxes: Iterable[Box], rois: Mapping[str, Polygon]) -> dict[str, int]:
    """Conta as caixas cujo ponto de apoio cai no polígono de cada via.

    Caixas fora de todas as ROIs são ignoradas; se ROIs se sobrepõem, vale a primeira em ROADS.
    """
    counts = dict.fromkeys(ROADS, 0)
    for box in boxes:
        p = anchor(box)
        for road in ROADS:
            if road in rois and point_in_polygon(p, rois[road]):
                counts[road] += 1
                break
    return counts


def parse_rois(data: Mapping[str, object]) -> dict[str, Polygon]:
    rois: dict[str, Polygon] = {}
    for road, pts in data.items():
        if road not in ROADS:
            raise ValueError(f"via inválida nas ROIs: {road!r} (use {ROADS})")
        poly = [(float(x), float(y)) for x, y in pts]  # type: ignore[union-attr]
        if len(poly) < 3:
            raise ValueError(f"ROI da via {road} precisa de pelo menos 3 pontos")
        rois[road] = poly
    return rois


def load_rois(path: Path) -> dict[str, Polygon]:
    """Lê {"N": [[x, y], ...], ...}; chaves iniciadas por "_" são comentários."""
    data = json.loads(path.read_text())
    return parse_rois({k: v for k, v in data.items() if not k.startswith("_")})


class Smoother:
    """Mediana das últimas `window` leituras por via, para a fila não oscilar entre frames."""

    def __init__(self, window: int = 5) -> None:
        if window < 1:
            raise ValueError("window precisa ser >= 1")
        self._hist = {road: deque(maxlen=window) for road in ROADS}

    def update(self, counts: Mapping[str, int]) -> dict[str, int]:
        out = {}
        for road in ROADS:
            self._hist[road].append(counts.get(road, 0))
            out[road] = statistics.median_low(self._hist[road])
        return out


class TrackHold:
    """Mantém um objeto rastreado contando por até `hold_frames` frames sem detecção.

    Recebe (id do rastreador, caixa) a cada frame. Se o detector falha por um ou dois frames, o
    objeto continua na fila com a última caixa conhecida, em vez de sumir e voltar.
    """

    def __init__(self, hold_frames: int = 5) -> None:
        if hold_frames < 0:
            raise ValueError("hold_frames precisa ser >= 0")
        self._hold = hold_frames
        self._frame = 0
        self._last: dict[int, tuple[Box, int]] = {}

    def update(self, tracks: Iterable[tuple[int, Box]]) -> list[Box]:
        self._frame += 1
        for track_id, box in tracks:
            self._last[track_id] = (box, self._frame)
        self._last = {
            tid: (box, seen)
            for tid, (box, seen) in self._last.items()
            if self._frame - seen <= self._hold
        }
        return [box for box, _seen in self._last.values()]


class SimulatedCounter:
    """Fila simulada: cada via sobe ou desce no máximo 1 veículo por leitura (passeio aleatório)."""

    def __init__(self, seed: int | None = None, max_per_road: int = 10) -> None:
        self._rng = random.Random(seed)
        self._max = max_per_road
        self._counts = {road: self._rng.randint(0, max_per_road) for road in ROADS}

    def counts(self) -> dict[str, int]:
        for road in ROADS:
            step = self._rng.choice((-1, 0, 1))
            self._counts[road] = min(self._max, max(0, self._counts[road] + step))
        return dict(self._counts)
