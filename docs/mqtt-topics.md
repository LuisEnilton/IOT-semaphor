# Contrato MQTT

Broker: Mosquitto no Raspberry Pi (porta 1883). `<id>` = `cruzamento1` (ver `firmware/include/config.h`).
Vias: `N`, `L`, `S`, `O`. Estados: `red`, `yellow`, `green`, `off`, `flash_yellow`.

| Tópico | Direção | QoS | Retained | Payload |
|---|---|---|---|---|
| `semaphor/<id>/cmd` | Pi → ESP32 | 1 | não | `{"roads": {"N":"green","S":"green","L":"red","O":"red"}}` (vias omitidas não mudam) |
| `semaphor/<id>/state` | ESP32 → Pi | 0 | sim | `{"safe_mode": false, "roads": {"N":"green", ...}}` |
| `semaphor/<id>/status` | ESP32 → Pi | 1 | sim | `online` / `offline` (Last Will) |

**Modo seguro:** sem comando por 10 s (`COMMAND_TIMEOUT_MS`) o ESP32 pisca amarelo em todas as vias.
Quem decide conflitos (ex.: verde simultâneo em vias cruzadas) é o Pi; o ESP32 só executa.
