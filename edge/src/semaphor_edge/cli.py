"""Ferramentas de linha de comando para testar a comunicação Pi <-> ESP32."""

import argparse
import time

import paho.mqtt.client as mqtt

from .config import Config
from .protocol import ROADS, STATES, build_cmd, topic


def _client(cfg: Config) -> mqtt.Client:
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    c.connect(cfg.mqtt_host, cfg.mqtt_port)
    return c


def cmd_monitor(cfg: Config, _args) -> None:
    c = _client(cfg)
    c.on_message = lambda _c, _u, m: print(f"{m.topic}  {m.payload.decode()}")
    c.subscribe(f"semaphor/{cfg.intersection_id}/#")
    c.loop_forever()


def cmd_set(cfg: Config, args) -> None:
    try:
        roads = dict(pair.split("=", 1) for pair in args.roads)
        payload = build_cmd(roads)
    except ValueError as e:
        raise SystemExit(f"erro: {e}") from None
    c = _client(cfg)
    c.loop_start()
    c.publish(topic(cfg.intersection_id, "cmd"), payload, qos=1).wait_for_publish()
    c.loop_stop()


# Mesmo ciclo do modo local do firmware: (estado da via A, estado da via B, segundos).
DEMO_CYCLE = [
    ("green", "red", 5),
    ("yellow", "red", 2),
    ("red", "red", 1),
    ("red", "green", 5),
    ("red", "yellow", 2),
    ("red", "red", 1),
]


def cmd_demo(cfg: Config, _args) -> None:
    """Ciclo A/B com amarelo e vermelho geral; reenvia o comando a cada 1 s (heartbeat)."""
    c = _client(cfg)
    c.loop_start()
    while True:
        for a, b, seconds in DEMO_CYCLE:
            payload = build_cmd({"N": a, "S": a, "L": b, "O": b})
            for _ in range(seconds):
                c.publish(topic(cfg.intersection_id, "cmd"), payload, qos=1)
                time.sleep(1)


def main() -> None:
    p = argparse.ArgumentParser(prog="semaphor-edge")
    sub = p.add_subparsers(required=True)
    sub.add_parser("monitor", help="imprime todas as mensagens do cruzamento").set_defaults(
        fn=cmd_monitor
    )
    s = sub.add_parser("set", help="define estados, ex.: set N=green S=green L=red O=red")
    s.add_argument("roads", nargs="+", metavar="VIA=ESTADO", help=f"vias {ROADS}, estados {STATES}")
    s.set_defaults(fn=cmd_set)
    sub.add_parser("demo", help="ciclo A/B com amarelo e vermelho geral").set_defaults(fn=cmd_demo)
    args = p.parse_args()
    args.fn(Config.load(), args)
