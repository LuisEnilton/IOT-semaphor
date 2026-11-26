import pytest

from semaphor_edge.phases import Phase, PhaseController, Timing, roads_for, start_phase_for
from semaphor_edge.protocol import has_conflict


def run_cycle(ctrl: PhaseController, until: float, dt: float = 0.05):
    """Simula o loop e devolve [(instante, fase)] a cada troca."""
    t, changes = 0.0, [(0.0, ctrl.phase)]
    while t < until:
        t = round(t + dt, 6)
        if ctrl.update(t):
            changes.append((t, ctrl.phase))
    return changes


def test_no_phase_has_conflict():
    for phase in Phase:
        assert not has_conflict(roads_for(phase)), phase


def test_cycle_order_and_durations():
    ctrl = PhaseController(0.0, Timing(green_s=5, yellow_s=2, all_red_s=1))
    changes = run_cycle(ctrl, 17.5)
    assert [p for _, p in changes] == [
        Phase.RED_AFTER_B,
        Phase.A_GREEN,
        Phase.A_YELLOW,
        Phase.RED_AFTER_A,
        Phase.B_GREEN,
        Phase.B_YELLOW,
        Phase.RED_AFTER_B,
        Phase.A_GREEN,
    ]
    times = [t for t, _ in changes]
    assert times == pytest.approx([0, 1, 6, 8, 9, 14, 16, 17])


def test_green_always_followed_by_yellow_then_all_red():
    ctrl = PhaseController(0.0)
    seq = [p for _, p in run_cycle(ctrl, 100)]
    for prev, nxt in zip(seq, seq[1:], strict=False):
        if prev in (Phase.A_GREEN, Phase.B_GREEN):
            assert nxt in (Phase.A_YELLOW, Phase.B_YELLOW)
        if prev in (Phase.A_YELLOW, Phase.B_YELLOW):
            assert roads_for(nxt) == dict.fromkeys(roads_for(nxt), "red")


def test_advances_at_most_one_phase_per_update():
    ctrl = PhaseController(0.0)
    assert ctrl.update(1000.0)  # loop atrasou muito
    assert ctrl.phase is Phase.A_GREEN  # não pulou direto para outra fase


def test_green_policy_sets_green_duration_per_group():
    ctrl = PhaseController(0.0, Timing(), green_policy=lambda g: 3.0 if g == "A" else 7.0)
    changes = dict((p, t) for t, p in run_cycle(ctrl, 15))
    assert changes[Phase.A_YELLOW] - changes[Phase.A_GREEN] == pytest.approx(3.0)
    assert changes[Phase.B_YELLOW] - changes[Phase.B_GREEN] == pytest.approx(7.0)


def test_invalid_timing_rejected():
    with pytest.raises(ValueError):
        Timing(green_s=0)
    with pytest.raises(ValueError):
        PhaseController(0.0, green_policy=lambda _g: -1, start=Phase.RED_AFTER_B).update(2.0)


@pytest.mark.parametrize(
    ("roads", "expected"),
    [
        (None, Phase.RED_AFTER_B),
        ({"N": "red", "S": "red", "L": "red", "O": "red"}, Phase.RED_AFTER_B),
        ({"N": "green", "S": "green", "L": "red", "O": "red"}, Phase.A_YELLOW),
        ({"N": "red", "S": "red", "L": "yellow", "O": "yellow"}, Phase.B_YELLOW),
        ({"N": "flash_yellow", "L": "flash_yellow"}, Phase.RED_AFTER_B),
    ],
)
def test_start_phase_never_cuts_green(roads, expected):
    assert start_phase_for(roads) is expected
