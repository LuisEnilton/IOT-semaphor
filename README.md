# Semáforo inteligente (IoT)

Maquete de cruzamento com 4 vias. **ESP32** controla os LEDs; **Raspberry Pi 5** roda o algoritmo de fila
(e, futuramente, visão computacional). Comunicação por **MQTT** — contrato em [docs/mqtt-topics.md](docs/mqtt-topics.md).

```
firmware/  PlatformIO (ESP32)          edge/   Python (Raspberry Pi)
infra/     config do Mosquitto         docs/   documentação
```

## Setup (colaboradores)

Pré-requisitos no notebook: Python ≥ 3.10, VS Code (instale as extensões recomendadas), Docker (opcional).

1. `make setup` — cria `edge/.venv`, `edge/.env` e `firmware/include/secrets.h`.
2. Edite `firmware/include/secrets.h` com o Wi-Fi e o IP/hostname do broker (**nunca commite**).
3. Broker: no Pi use `make setup-pi` (uma vez). Sem o Pi, use `make broker` (Docker) e aponte `MQTT_HOST` para o seu IP.
4. Firmware: `make fw-build` → `make fw-upload` (ESP32 via USB) → `make fw-monitor`.
   Se o upload falhar por permissão: `sudo usermod -aG dialout $USER` e reabra a sessão.
5. Teste ponta a ponta: `make monitor` num terminal e `make demo` em outro (ou
   `edge/.venv/bin/semaphor-edge set N=green S=green L=red O=red`).

### Raspberry Pi
Pi OS 64-bit. Clone o repo, rode `make setup-pi`. Para desenvolver nele, use **VS Code Remote-SSH**
(`ssh <usuario>@raspberrypi.local`). Ele usa venv com `--system-site-packages` porque o `picamera2`
vem do apt.

## Fluxo de trabalho
- Branch por funcionalidade + Pull Request; o CI roda lint, testes e build do firmware.
- Mudou o protocolo? Atualize `docs/mqtt-topics.md`, `firmware/` e `edge/protocol.py` juntos.
- Antes de commitar: `make lint test`.
