"""CLI do Pi: controlador de fases (run) e ferramentas de teste (monitor, set)."""

import argparse
import logging

import paho.mqtt.client as mqtt

from .config import Config
from .phases import Timing
from .policy import QueueParams, QueuePolicy
from .protocol import ROADS, STATES, build_cmd, topic
from .runner import run
from .simulation import compare
from .traffic import SimulatedTraffic, parse_arrivals


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


def _timing(cfg: Config, args) -> Timing:
    return Timing(
        green_s=args.green if args.green is not None else cfg.green_s,
        yellow_s=args.yellow if args.yellow is not None else cfg.yellow_s,
        all_red_s=args.all_red if args.all_red is not None else cfg.all_red_s,
    )


def _queue_params(cfg: Config) -> QueueParams:
    return QueueParams(cfg.min_green_s, cfg.max_green_s, cfg.sec_per_vehicle)


def cmd_run(cfg: Config, args) -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S"
    )
    try:
        timing = _timing(cfg, args)
        if not args.simulado:
            run(cfg, timing, heartbeat_s=cfg.heartbeat_s)
            return
        params = _queue_params(cfg)
        arrivals = parse_arrivals(args.chegadas or cfg.arrivals)
        traffic = SimulatedTraffic(arrivals, headway_s=params.sec_per_vehicle)
        logging.getLogger("semaphor_edge").info(
            "tráfego SIMULADO, chegadas/s %s; verde de %.0f a %.0f s conforme a fila",
            arrivals,
            params.min_green_s,
            params.max_green_s,
        )
        run(
            cfg,
            timing,
            heartbeat_s=cfg.heartbeat_s,
            green_policy=QueuePolicy(traffic, params),
            on_tick=traffic.update,
        )
    except ValueError as e:
        raise SystemExit(f"erro: {e}") from None


def cmd_simular(cfg: Config, args) -> None:
    try:
        timing = _timing(cfg, args)
        params = _queue_params(cfg)
        arrivals = parse_arrivals(args.chegadas or cfg.arrivals)
    except ValueError as e:
        raise SystemExit(f"erro: {e}") from None
    print(f"Chegadas (veículos/s): {arrivals}")
    print(
        f"Duração simulada: {args.duracao:.0f} s, {args.sementes} rodadas. Ciclo fixo com verde "
        f"{timing.green_s:.0f} s; adaptativo com verde de {params.min_green_s:.0f} a "
        f"{params.max_green_s:.0f} s.\n"
    )
    print(f"{'método':<20}{'espera média':>14}{'fila máxima':>13}{'atendidos':>11}")
    for s in compare(arrivals, args.duracao, timing, params, args.sementes):
        print(f"{s.name:<20}{s.avg_wait_s:>12.1f} s{s.max_queue:>13}{s.served:>11}")


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
    r.add_argument(
        "--simulado",
        action="store_true",
        help="usa tráfego simulado e o algoritmo de fila (verde dinâmico)",
    )
    r.add_argument(
        "--chegadas", help="taxas por via, ex.: N=0.4,S=0.3,L=0.1,O=0.1 (padrão: ARRIVALS)"
    )
    r.set_defaults(fn=cmd_run)

    m = sub.add_parser("simular", help="compara ciclo fixo e algoritmo de fila (offline, sem MQTT)")
    m.add_argument("--duracao", type=float, default=1800, help="segundos simulados (padrão 1800)")
    m.add_argument("--sementes", type=int, default=5, help="rodadas com sementes diferentes")
    m.add_argument("--chegadas", help="taxas por via, ex.: N=0.4,S=0.3,L=0.1,O=0.1")
    m.add_argument("--green", type=float, help="verde do ciclo fixo (padrão: GREEN_S)")
    m.add_argument("--yellow", type=float, help="amarelo (padrão: YELLOW_S)")
    m.add_argument("--all-red", type=float, help="vermelho geral (padrão: ALL_RED_S)")
    m.set_defaults(fn=cmd_simular)
    args = p.parse_args()
    args.fn(Config.load(), args)
