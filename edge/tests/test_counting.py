import json

import pytest

from semaphor_edge.counting import (
    SimulatedCounter,
    Smoother,
    TrackHold,
    anchor,
    count_by_roi,
    load_rois,
    parse_rois,
    point_in_polygon,
)
from semaphor_edge.protocol import ROADS

SQUARE = [(0, 0), (10, 0), (10, 10), (0, 10)]


def test_point_in_polygon():
    assert point_in_polygon((5, 5), SQUARE)
    assert not point_in_polygon((15, 5), SQUARE)
    assert not point_in_polygon((5, -1), SQUARE)
    tri = [(0, 0), (10, 0), (0, 10)]
    assert point_in_polygon((2, 2), tri)
    assert not point_in_polygon((8, 8), tri)


def test_anchor_is_bottom_center():
    assert anchor((0, 0, 10, 20)) == (5, 20)


def test_count_by_roi_assigns_and_ignores_outside():
    rois = {"N": SQUARE, "S": [(20, 0), (30, 0), (30, 10), (20, 10)]}
    boxes = [
        (2, 0, 4, 5),  # N
        (6, 2, 8, 8),  # N
        (22, 0, 28, 9),  # S
        (50, 50, 60, 60),  # fora de tudo
    ]
    assert count_by_roi(boxes, rois) == {"N": 2, "L": 0, "S": 1, "O": 0}


def test_count_by_roi_always_has_all_roads():
    assert count_by_roi([], {}) == dict.fromkeys(ROADS, 0)


def test_parse_rois_validation():
    with pytest.raises(ValueError):
        parse_rois({"X": [[0, 0], [1, 0], [0, 1]]})
    with pytest.raises(ValueError):
        parse_rois({"N": [[0, 0], [1, 0]]})


def test_load_rois_skips_comments(tmp_path):
    f = tmp_path / "rois.json"
    f.write_text(json.dumps({"_comentario": "x", "N": [[0, 0], [10, 0], [10, 10]]}))
    assert load_rois(f) == {"N": [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]}


def test_smoother_filters_single_frame_spikes():
    s = Smoother(window=3)
    s.update({"N": 2})
    s.update({"N": 2})
    assert s.update({"N": 9})["N"] == 2  # pico isolado não muda a fila
    assert s.update({"N": 9})["N"] == 9


def test_track_hold_bridges_missed_frames():
    hold = TrackHold(hold_frames=2)
    a, b = (0, 0, 10, 10), (20, 0, 30, 10)
    assert hold.update([(1, a), (2, b)]) == [a, b]
    assert hold.update([(1, a)]) == [a, b]  # 2 falhou 1 frame: continua
    assert hold.update([(1, a)]) == [a, b]  # 2 falhou 2 frames: continua
    assert hold.update([(1, a)]) == [a]  # 3 frames sem 2: sai da fila


def test_track_hold_uses_latest_box():
    hold = TrackHold(hold_frames=1)
    hold.update([(7, (0, 0, 10, 10))])
    assert hold.update([(7, (5, 0, 15, 10))]) == [(5, 0, 15, 10)]


def test_track_hold_zero_means_no_memory():
    hold = TrackHold(hold_frames=0)
    assert hold.update([(1, (0, 0, 1, 1))]) == [(0, 0, 1, 1)]
    assert hold.update([]) == []


def test_simulated_counter_is_reproducible_and_bounded():
    a, b = SimulatedCounter(seed=1, max_per_road=5), SimulatedCounter(seed=1, max_per_road=5)
    for _ in range(50):
        ca = a.counts()
        assert ca == b.counts()
        assert set(ca) == set(ROADS)
        assert all(0 <= v <= 5 for v in ca.values())
