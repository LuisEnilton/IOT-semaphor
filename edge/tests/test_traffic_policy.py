import pytest

from semaphor_edge.phases import Phase, PhaseController, Timing, roads_for
from semaphor_edge.policy import QueueParams, QueuePolicy
from semaphor_edge.simulation import compare, simulate
from semaphor_edge.traffic import SimulatedTraffic, parse_arrivals

ALL_RED = dict.fromkeys("NLSO", "red")
A_GREEN = roads_for(Phase.A_GREEN)


class FixedCounter:
    def __init__(self, counts):
        self._counts = counts

    def counts(self):
        return self._counts


def test_parse_arrivals():
    assert parse_arrivals("N=0.4, s=0.2") == {"N": 0.4, "L": 0.0, "S": 0.2, "O": 0.0}
    with pytest.raises(ValueError):
        parse_arrivals("X=1")
    with pytest.raises(ValueError):
        parse_arrivals("N=-1")


def test_queue_grows_on_red_and_drains_on_green():
    t = SimulatedTraffic({"N": 1.0}, headway_s=1.0, seed=1)
    for i in range(11):  # 10 s de vermelho, 1 veículo/s
        t.update(float(i), ALL_RED)
    assert t.counts()["N"] == 10
    t.arrivals["N"] = 0.0  # para de chegar
    for i in range(11, 31):  # 20 s de verde: sai 1 veículo/s
        t.update(float(i), A_GREEN)
    assert t.counts()["N"] == 0
    assert t.stats.served == 10


def test_green_proportional_to_largest_queue_in_group():
    p = QueuePolicy(FixedCounter({}), QueueParams(3, 15, 1.0))
    assert p.green_for({"N": 7, "S": 2, "L": 30, "O": 0}, "A") == 7  # maior fila de A
    assert p.green_for({"N": 0, "S": 0}, "A") == 3  # mínimo
    assert p.green_for({"L": 30}, "B") == 15  # máximo


def test_invalid_params():
    with pytest.raises(ValueError):
        QueueParams(min_green_s=10, max_green_s=5)


def test_no_road_starves_even_if_counter_says_empty():
    """E3.2: com a contagem de B zerada e a de A enorme, B ainda recebe verde a cada ciclo.

    Pior caso sem verde para B: amarelo B + vermelho + verde A máximo + amarelo A + vermelho.
    """
    policy = QueuePolicy(FixedCounter({"N": 99, "S": 99, "L": 0, "O": 0}), QueueParams(3, 15))
    timing = Timing(yellow_s=2, all_red_s=1)
    ctrl = PhaseController(0.0, timing, policy)
    t, last_b_green, worst_red = 0.0, 0.0, 0.0
    while t < 300:
        t = round(t + 0.1, 6)
        ctrl.update(t)
        if ctrl.phase is Phase.B_GREEN:
            last_b_green = t
        worst_red = max(worst_red, t - last_b_green)
    assert (
        worst_red <= 15 + 2 + 1 + 3 + 0.2
    )  # verde A máx + amarelo + vermelho + verde B mín... de folga


def test_adaptive_beats_fixed_when_unbalanced():
    fixed, adaptive = compare({"N": 0.35, "S": 0.3, "L": 0.1, "O": 0.1}, 600, Timing(), seeds=2)
    assert adaptive.avg_wait_s < fixed.avg_wait_s


def test_simulation_is_reproducible():
    a = simulate({"N": 0.2, "L": 0.2}, 120, Timing(), adaptive=True, seed=3)
    b = simulate({"N": 0.2, "L": 0.2}, 120, Timing(), adaptive=True, seed=3)
    assert a.avg_wait_s == b.avg_wait_s and a.served == b.served
