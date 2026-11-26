"""Ferramentas de linha de comando para testar a comunicação Pi <-> ESP32."""

import argparse
import sys
import time
from pathlib import Path

import paho.mqtt.client as mqtt

from .config import Config
from .counting import SimulatedCounter, load_rois
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


def _fmt_counts(counts: dict[str, int]) -> str:
    return "  ".join(f"{road}={counts[road]:2d}" for road in ROADS)


def _yolo_counter(cfg: Config):
    rois_file = Path(cfg.rois_path)
    if rois_file.is_file():
        rois = load_rois(rois_file)
    else:
        print(
            f"aviso: {rois_file} não existe; todas as vias vão contar 0 (copie rois.example.json)"
        )
        rois = {}
    try:
        from .vision import YoloCounter
    except ImportError as e:  # pragma: no cover - depende do ambiente
        sys.exit(f"erro: {e}. No Pi, rode 'make setup-vision' (ver docs/visao.md)")
    return YoloCounter(
        cfg.vision_model,
        rois,
        cfg.vision_classes,
        conf=cfg.vision_conf,
        imgsz=cfg.vision_imgsz,
        smooth_window=cfg.vision_smooth,
        track=cfg.vision_track,
        hold_frames=cfg.vision_hold,
    )


def cmd_count(cfg: Config, args) -> None:
    """Imprime a fila por via continuamente (câmera + YOLO, ou simulada com --sim)."""
    if args.sim:
        counter = SimulatedCounter(seed=args.seed)
        while True:
            print(_fmt_counts(counter.counts()), flush=True)
            time.sleep(args.interval)

    counter = _yolo_counter(cfg)
    if args.show:
        import cv2

        from .vision import draw
    try:
        while True:
            t0 = time.monotonic()
            counts = counter.counts()
            ms = (time.monotonic() - t0) * 1000
            print(
                f"{_fmt_counts(counts)}  ({len(counter.last_boxes)} det, {ms:.0f} ms)", flush=True
            )
            if args.show:
                cv2.imshow(
                    "semaphor", draw(counter.last_frame, counter.rois, counter.last_boxes, counts)
                )
                if cv2.waitKey(1) == ord("q"):
                    break
            if args.interval:
                time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        counter.close()


def cmd_snapshot(_cfg: Config, args) -> None:
    """Salva um frame da câmera (para desenhar as ROIs ou montar o dataset)."""
    import cv2

    from .vision import Camera

    cam = Camera()
    try:
        time.sleep(1)  # deixa o auto-exposição estabilizar
        out = Path(args.output or f"snapshots/{time.strftime('%Y%m%d-%H%M%S')}.jpg")
        out.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out), cam.read())
        print(f"salvo em {out}")
    finally:
        cam.close()


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
    c = sub.add_parser("count", help="mostra a fila de veículos por via (câmera + YOLO)")
    c.add_argument("--sim", action="store_true", help="contagem simulada, sem câmera")
    c.add_argument("--seed", type=int, default=None, help="semente da simulação")
    c.add_argument("--show", action="store_true", help="janela com caixas e ROIs (precisa de tela)")
    c.add_argument("--interval", type=float, default=None, help="pausa entre leituras (s)")
    c.set_defaults(fn=cmd_count)
    sn = sub.add_parser("snapshot", help="salva um frame da câmera em snapshots/")
    sn.add_argument("-o", "--output", help="arquivo de saída (.jpg)")
    sn.set_defaults(fn=cmd_snapshot)
    args = p.parse_args()
    if getattr(args, "interval", 0) is None:
        args.interval = 1.0 if args.sim else 0.0
    args.fn(Config.load(), args)
