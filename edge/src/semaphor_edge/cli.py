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
    roads = dict(pair.split("=", 1) for pair in args.roads)
    c = _client(cfg)
    c.loop_start()
    c.publish(topic(cfg.intersection_id, "cmd"), build_cmd(roads), qos=1).wait_for_publish()
    c.loop_stop()


def cmd_demo(cfg: Config, _args) -> None:
    """Alterna N/S e L/O a cada 4 s (reenvia a cada 2 s para evitar o modo seguro)."""
    c = _client(cfg)
    c.loop_start()
    phases = [
        {"N": "green", "S": "green", "L": "red", "O": "red"},
        {"N": "red", "S": "red", "L": "green", "O": "green"},
    ]
    while True:
        for phase in phases:
            for _ in range(2):
                c.publish(topic(cfg.intersection_id, "cmd"), build_cmd(phase), qos=1)
                time.sleep(2)


def main() -> None:
    p = argparse.ArgumentParser(prog="semaphor-edge")
    sub = p.add_subparsers(required=True)
    sub.add_parser("monitor", help="imprime todas as mensagens do cruzamento").set_defaults(
        fn=cmd_monitor
    )
    s = sub.add_parser("set", help="define estados, ex.: set N=green S=green L=red O=red")
    s.add_argument("roads", nargs="+", metavar="VIA=ESTADO", help=f"vias {ROADS}, estados {STATES}")
    s.set_defaults(fn=cmd_set)
    sub.add_parser("demo", help="ciclo simples de teste").set_defaults(fn=cmd_demo)
    args = p.parse_args()
    args.fn(Config.load(), args)
