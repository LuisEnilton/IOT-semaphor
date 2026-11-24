# Contrato MQTT

Broker: Mosquitto no Raspberry Pi (porta 1883). `<id>` = `cruzamento1` (ver `firmware/include/config.h`).
Vias: `N`, `L`, `S`, `O`. Estados: `red`, `yellow`, `green`, `off`, `flash_yellow`.

| Tópico | Direção | QoS | Retained | Payload |
|---|---|---|---|---|
| `semaphor/<id>/cmd` | Pi → ESP32 | 1 | não | `{"roads": {"N":"green","S":"green","L":"red","O":"red"}}` (vias omitidas não mudam) |
| `semaphor/<id>/state` | ESP32 → Pi | 0 | sim | `{"mode": "remote", "roads": {"N":"green", ...}}` |
| `semaphor/<id>/status` | ESP32 → Pi | 1 | sim | `online` / `offline` (Last Will) |

Semáforos físicos: S1 = `N`, S2 = `L`, S3 = `S`, S4 = `O`.
Via **A** = `N` + `S`; via **B** = `L` + `O`.

**Campo `mode` do `state`:**

| Valor | Significado |
|---|---|
| `local` | Sem comandos do Pi: o ESP32 roda o ciclo fixo (A verde 5 s → A amarelo 2 s → vermelho geral 1 s → B verde 5 s → B amarelo 2 s → vermelho geral 1 s) |
| `remote` | O ESP32 está seguindo os comandos do Pi |
| `test` | Sequência de teste dos 12 LEDs (disparada por `t` na serial) |

**Timeout:** sem comando por 10 s (`COMMAND_TIMEOUT_MS`), o ESP32 volta ao modo `local`, passando
pelo amarelo se alguma via estava aberta. O Pi deve reenviar o comando periodicamente (heartbeat).

**Comandos rejeitados** (o ESP32 ignora e só registra na serial): JSON inválido, estado desconhecido,
comando recebido durante o modo `test`, ou resultado com **conflito**: alguma via A e alguma via B em
`green`/`yellow` ao mesmo tempo. Como vias omitidas mantêm o estado atual, um comando parcial também
é rejeitado se conflitar com o estado vigente: prefira mandar as 4 vias.
O Pi continua responsável pela lógica de fases (amarelo e vermelho geral entre trocas).
