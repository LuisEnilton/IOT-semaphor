"""CLI do Pi: controlador de fases (run) e ferramentas de teste (monitor, set)."""

import argparse
import logging

import paho.mqtt.client as mqtt

from .config import Config
from .phases import Timing
from .protocol import ROADS, STATES, build_cmd, topic
from .runner import run


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


def cmd_run(cfg: Config, args) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S"
    )
    try:
        timing = Timing(
            green_s=args.green if args.green is not None else cfg.green_s,
            yellow_s=args.yellow if args.yellow is not None else cfg.yellow_s,
            all_red_s=args.all_red if args.all_red is not None else cfg.all_red_s,
        )
        run(cfg, timing, heartbeat_s=cfg.heartbeat_s)
    except ValueError as e:
        raise SystemExit(f"erro: {e}") from None


def main() -> None:
    p = argparse.ArgumentParser(prog="semaphor-edge")
    sub = p.add_subparsers(required=True)
    sub.add_parser("monitor", help="imprime todas as mensagens do cruzamento").set_defaults(
        fn=cmd_monitor
    )
    s = sub.add_parser("set", help="define estados, ex.: set N=green S=green L=red O=red")
    s.add_argument("roads", nargs="+", metavar="VIA=ESTADO", help=f"vias {ROADS}, estados {STATES}")
    s.set_defaults(fn=cmd_set)
    r = sub.add_parser(
        "run", help="controlador de fases: comanda o ESP32 (tempos do .env ou das opções)"
    )
    r.add_argument("--green", type=float, help="segundos de verde (padrão: GREEN_S)")
    r.add_argument("--yellow", type=float, help="segundos de amarelo (padrão: YELLOW_S)")
    r.add_argument("--all-red", type=float, help="segundos de vermelho geral (padrão: ALL_RED_S)")
    r.set_defaults(fn=cmd_run)
    args = p.parse_args()
    args.fn(Config.load(), args)
