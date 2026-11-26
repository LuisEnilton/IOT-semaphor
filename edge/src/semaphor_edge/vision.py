"""Contagem de veículos com câmera do Pi + Ultralytics YOLO (formato NCNN recomendado).

Depende de hardware e do extra `vision` (pip install -e "edge[vision]"); picamera2 vem do apt.
Os imports pesados ficam dentro das funções para o resto do pacote (e o CI) não precisar deles.
"""

from collections.abc import Sequence

from .counting import Box, Polygon, Smoother, TrackHold, anchor, count_by_roi

ROAD_COLORS = {"N": (0, 0, 255), "L": (0, 200, 0), "S": (255, 0, 0), "O": (0, 200, 200)}


class Camera:
    """Picamera2 entregando frames numpy no formato que OpenCV/Ultralytics esperam (BGR)."""

    def __init__(self, size: tuple[int, int] = (640, 480)) -> None:
        from picamera2 import Picamera2

        self._cam = Picamera2()
        # "RGB888" no picamera2 = bytes em ordem BGR, que é o que o OpenCV usa.
        cfg = self._cam.create_video_configuration(main={"size": size, "format": "RGB888"})
        self._cam.configure(cfg)
        self._cam.start()

    def read(self):
        return self._cam.capture_array()

    def close(self) -> None:
        self._cam.stop()
        self._cam.close()


# Limiar mínimo que o rastreador recebe: detecções fracas só servem para manter quem já é seguido.
TRACK_LOW_CONF = 0.1


def _write_tracker_cfg(conf: float, buffer_frames: int) -> str:
    """Gera o YAML do ByteTrack com histerese: entra com `conf`, se mantém com TRACK_LOW_CONF.

    O caminho é fixo por configuração (sobrescrito a cada execução), então não acumula arquivos.
    """
    import tempfile
    from pathlib import Path

    cfg = {
        "tracker_type": "bytetrack",
        "track_high_thresh": conf,  # 1ª associação (detecções confiáveis)
        "track_low_thresh": min(TRACK_LOW_CONF, conf),  # 2ª associação: só para tracks existentes
        "new_track_thresh": conf,  # para começar a contar um objeto novo
        "track_buffer": buffer_frames,  # frames em que um track perdido ainda pode ser retomado
        "match_thresh": 0.8,
        "fuse_score": True,
    }
    path = Path(tempfile.gettempdir()) / f"semaphor-bytetrack-{conf:g}-{buffer_frames}.yaml"
    path.write_text("".join(f"{k}: {v}\n" for k, v in cfg.items()))
    return str(path)


class YoloCounter:
    """Implementa VehicleCounter: captura, detecta, rastreia e conta por ROI (com suavização).

    Estabilização, da detecção para a contagem:
    - NMS agnóstico: o mesmo objeto não vira duas caixas com classes diferentes;
    - rastreamento ByteTrack (track=True): histerese de confiança e só conta objetos confirmados;
    - TrackHold: um objeto rastreado continua contando por `hold_frames` frames sem detecção;
    - Smoother: mediana das últimas `smooth_window` contagens por via.
    """

    def __init__(
        self,
        model_path: str,
        rois: dict[str, Polygon],
        classes: Sequence[str],
        conf: float = 0.4,
        imgsz: int = 640,
        smooth_window: int = 9,
        track: bool = True,
        hold_frames: int = 5,
        camera: Camera | None = None,
    ) -> None:
        from ultralytics import YOLO

        self.model = YOLO(model_path, task="detect")
        self.rois = rois
        self.conf = conf
        self.imgsz = imgsz
        self.class_ids = self._resolve_classes(classes)
        self.track = track
        self.hold = TrackHold(hold_frames)
        self.tracker_cfg = _write_tracker_cfg(conf, max(30, 2 * hold_frames)) if track else None
        self.camera = camera or Camera()
        self.smoother = Smoother(smooth_window)
        self.last_frame = None
        self.last_boxes: list[Box] = []

    def _resolve_classes(self, classes: Sequence[str]) -> list[int] | None:
        if not classes:
            return None  # todas as classes
        by_name = {name: i for i, name in self.model.names.items()}
        missing = [c for c in classes if c not in by_name]
        if missing:
            raise ValueError(f"classes desconhecidas pelo modelo: {missing}")
        return [by_name[c] for c in classes]

    def detect(self, frame) -> list[Box]:
        """Caixas dos veículos no frame (rastreadas e mantidas, se track=True)."""
        common = dict(imgsz=self.imgsz, classes=self.class_ids, agnostic_nms=True, verbose=False)
        if not self.track:
            result = self.model.predict(frame, conf=self.conf, **common)[0]
            return [tuple(map(float, b)) for b in result.boxes.xyxy.tolist()]

        result = self.model.track(
            frame,
            conf=min(TRACK_LOW_CONF, self.conf),
            persist=True,
            tracker=self.tracker_cfg,
            **common,
        )[0]
        ids = result.boxes.id
        tracks = []
        if ids is not None:  # None quando nenhum objeto está confirmado neste frame
            for tid, b in zip(ids.int().tolist(), result.boxes.xyxy.tolist(), strict=True):
                tracks.append((tid, tuple(map(float, b))))
        return self.hold.update(tracks)

    def counts(self) -> dict[str, int]:
        self.last_frame = self.camera.read()
        self.last_boxes = self.detect(self.last_frame)
        return self.smoother.update(count_by_roi(self.last_boxes, self.rois))

    def close(self) -> None:
        self.camera.close()


def draw(frame, rois: dict[str, Polygon], boxes: list[Box], counts: dict[str, int]):
    """Desenha ROIs, caixas e contagem sobre uma cópia do frame (para calibrar as ROIs)."""
    import cv2
    import numpy as np

    img = frame.copy()
    for road, poly in rois.items():
        color = ROAD_COLORS.get(road, (255, 255, 255))
        pts = np.array(poly, dtype=np.int32)
        cv2.polylines(img, [pts], isClosed=True, color=color, thickness=2)
        x, y = pts[0]
        cv2.putText(
            img,
            f"{road}: {counts.get(road, 0)}",
            (int(x), int(y) - 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            color,
            2,
        )
    for box in boxes:
        x1, y1, x2, y2 = map(int, box)
        cv2.rectangle(img, (x1, y1), (x2, y2), (255, 255, 255), 1)
        ax, ay = map(int, anchor(box))
        cv2.circle(img, (ax, ay), 4, (0, 255, 255), -1)
    return img
