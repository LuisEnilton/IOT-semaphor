import json

import pytest

from semaphor_edge.phases import Phase, Timing
from semaphor_edge.runner import Runner, StateMonitor

ALL_RED = {"N": "red", "S": "red", "L": "red", "O": "red"}
A_GREEN = {"N": "green", "S": "green", "L": "red", "O": "red"}


def make_runner(**kw):
    sent = []
    runner = Runner(lambda p: sent.append(json.loads(p)["roads"]), 0.0, Timing(), **kw)
    return runner, sent


def test_waits_for_state_then_starts_from_it():
    runner, sent = make_runner()
    runner.step(0.5)
    assert sent == []  # ainda esperando o state retido
    runner.observe_state("local", A_GREEN)
    runner.step(0.6)
    assert runner.controller.phase is Phase.A_YELLOW  # não corta o verde
    assert sent[-1]["N"] == "yellow"


def test_starts_without_state_after_timeout():
    runner, sent = make_runner(wait_state_s=2.0)
    runner.step(1.9)
    assert sent == []
    runner.step(2.0)
    assert sent == [ALL_RED]


def test_heartbeat_and_phase_change_publish():
    runner, sent = make_runner(heartbeat_s=1.0)
    runner.observe_state(None, None)
    t = 0.0
    while t < 10.0:
        runner.step(t)
        t = round(t + 0.05, 6)
    # 10 s => ~10 heartbeats + trocas de fase; nunca fica 1 s sem enviar
    assert len(sent) >= 10
    assert sent[0] == ALL_RED and A_GREEN in sent


def test_resync_when_esp32_returns_in_local_mode():
    runner, sent = make_runner()
    runner.observe_state(None, None)
    t = 0.0
    while t < 7.0:  # 1 s de vermelho geral + 5 s de A verde => A amarelo aos 6 s
        runner.step(t)
        t = round(t + 0.05, 6)
    # ESP32 reiniciou e voltou no ciclo local com a via B verde
    runner.observe_state("local", {"N": "red", "S": "red", "L": "green", "O": "green"})
    runner.step(t)
    assert runner.controller.phase is Phase.B_YELLOW  # não corta o verde da via B
    assert sent[-1]["L"] == "yellow"
    # Em remote, nada muda
    runner.observe_state("remote", sent[-1])
    runner.step(t + 0.05)
    assert runner.controller.phase is Phase.B_YELLOW


def test_heartbeat_must_be_below_esp32_timeout():
    with pytest.raises(ValueError):
        Runner(lambda _p: None, 0.0, heartbeat_s=10)


def test_monitor_ignores_state_before_pi_takes_over():
    m = StateMonitor()
    assert m.on_state(json.dumps({"mode": "local", "roads": A_GREEN}), []) is None


def test_monitor_reports_only_changes():
    m = StateMonitor()
    local = json.dumps({"mode": "local", "roads": A_GREEN})
    remote = json.dumps({"mode": "remote", "roads": A_GREEN})
    ok, text = m.on_state(local, [A_GREEN])
    assert not ok and "local" in text
    assert m.on_state(local, [A_GREEN]) is None  # não repete
    assert m.on_state(remote, [A_GREEN]) == (True, "ESP32 seguindo os comandos do Pi")
    ok, text = m.on_state(remote, [ALL_RED])
    assert not ok and "diverge" in text


def test_monitor_status():
    m = StateMonitor()
    assert m.on_status("online") == (True, "ESP32 online")
    assert m.on_status("online") is None
    ok, _ = m.on_status("offline")
    assert not ok
