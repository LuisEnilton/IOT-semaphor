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

    @classmethod
    def load(cls) -> "Config":
        _load_dotenv(Path.cwd() / ".env")
        return cls(
            mqtt_host=os.getenv("MQTT_HOST", "localhost"),
            mqtt_port=int(os.getenv("MQTT_PORT", "1883")),
            intersection_id=os.getenv("INTERSECTION_ID", "cruzamento1"),
        )
