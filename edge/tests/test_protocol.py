import json

import pytest

from semaphor_edge.protocol import build_cmd, topic


def test_build_cmd():
    assert json.loads(build_cmd({"N": "green"})) == {"roads": {"N": "green"}}


def test_invalid_road_or_state():
    with pytest.raises(ValueError):
        build_cmd({"X": "green"})
    with pytest.raises(ValueError):
        build_cmd({"N": "blue"})


def test_topic():
    assert topic("c1", "cmd") == "semaphor/c1/cmd"


def test_conflict_rejected():
    with pytest.raises(ValueError):
        build_cmd({"N": "green", "L": "yellow"})


def test_same_group_and_red_allowed():
    build_cmd({"N": "green", "S": "green", "L": "red", "O": "red"})
    build_cmd({"N": "flash_yellow", "L": "flash_yellow"})
