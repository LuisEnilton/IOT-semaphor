"""Contagem de veículos com câmera do Pi + Ultralytics YOLO (formato NCNN recomendado).

Depende de hardware e do extra `vision` (pip install -e "edge[vision]"); picamera2 vem do apt.
Os imports pesados ficam dentro das funções para o resto do pacote (e o CI) não precisar deles.
"""

from collections.abc import Sequence

from .counting import Box, Polygon, Smoother, anchor, count_by_roi

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


class YoloCounter:
    """Implementa VehicleCounter: captura, detecta e conta por ROI (com suavização)."""

    def __init__(
        self,
        model_path: str,
        rois: dict[str, Polygon],
        classes: Sequence[str],
        conf: float = 0.4,
        imgsz: int = 640,
        smooth_window: int = 5,
        camera: Camera | None = None,
    ) -> None:
        from ultralytics import YOLO

        self.model = YOLO(model_path, task="detect")
        self.rois = rois
        self.conf = conf
        self.imgsz = imgsz
        self.class_ids = self._resolve_classes(classes)
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
        result = self.model.predict(
            frame, imgsz=self.imgsz, conf=self.conf, classes=self.class_ids, verbose=False
        )[0]
        return [tuple(map(float, b)) for b in result.boxes.xyxy.tolist()]

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
