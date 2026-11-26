import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


@dataclass(frozen=True)
class Config:
    mqtt_host: str
    mqtt_port: int
    intersection_id: str
    green_s: float = 5.0
    yellow_s: float = 2.0
    all_red_s: float = 1.0
    heartbeat_s: float = 1.0
    min_green_s: float = 3.0
    max_green_s: float = 15.0
    sec_per_vehicle: float = 1.0
    arrivals: str = "N=0.35,S=0.3,L=0.1,O=0.1"

    @classmethod
    def load(cls) -> "Config":
        _load_dotenv(Path.cwd() / ".env")
        return cls(
            mqtt_host=os.getenv("MQTT_HOST", "localhost"),
            mqtt_port=int(os.getenv("MQTT_PORT", "1883")),
            intersection_id=os.getenv("INTERSECTION_ID", "cruzamento1"),
            green_s=float(os.getenv("GREEN_S", "5")),
            yellow_s=float(os.getenv("YELLOW_S", "2")),
            all_red_s=float(os.getenv("ALL_RED_S", "1")),
            heartbeat_s=float(os.getenv("HEARTBEAT_S", "1")),
            min_green_s=float(os.getenv("MIN_GREEN_S", "3")),
            max_green_s=float(os.getenv("MAX_GREEN_S", "15")),
            sec_per_vehicle=float(os.getenv("SEC_PER_VEHICLE", "1")),
            arrivals=os.getenv("ARRIVALS", "N=0.35,S=0.3,L=0.1,O=0.1"),
        )
