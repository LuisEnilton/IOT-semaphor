# AGENTS.md

Guia para agentes de código (e pessoas) que vão trabalhar neste repositório. Leia antes de editar.
Arquitetura e setup para humanos: [README.md](README.md). Contrato MQTT: [docs/mqtt-topics.md](docs/mqtt-topics.md).

## Resumo do projeto

Semáforo inteligente em maquete: cruzamento com **4 vias** (`N`, `L`, `S`, `O` = norte, leste, sul, oeste).

- **ESP32** (`firmware/`, C++/Arduino via PlatformIO): só **executa**. Recebe o estado desejado das vias
  por MQTT, acende os LEDs e publica o estado real.
- **Raspberry Pi 5** (`edge/`, Python): **decide**. Hospeda o broker Mosquitto e vai rodar o algoritmo de
  fila e a visão computacional (câmera oficial do Pi).
- **MQTT** (Mosquitto, porta 1883, anônimo, sem TLS, só para rede local) liga os dois.

Idioma do projeto: **português** (docs, mensagens de commit, logs e textos da CLI). Identificadores de
código em inglês.

## Estrutura

```
firmware/
  platformio.ini            board esp32dev, libs PubSubClient e ArduinoJson
  include/config.h          ID do cruzamento, pinos (sem[4][3]), vias A/B, tempos do ciclo local e timeout
  include/secrets.example.h modelo de Wi-Fi/broker (secrets.h é local e ignorado pelo git)
  src/main.cpp              Wi-Fi/MQTT não bloqueantes, modos local/remote/test, LEDs, validação de conflito
edge/
  pyproject.toml            pacote semaphor-edge (paho-mqtt); extras dev: pytest, ruff, platformio
  .env.example              MQTT_HOST, MQTT_PORT, INTERSECTION_ID (.env é local)
  src/semaphor_edge/
    config.py               lê .env + variáveis de ambiente
    protocol.py             ROADS, STATES, ROAD_GROUP, has_conflict(), build_cmd() com validação
    cli.py                  semaphor-edge monitor | set VIA=ESTADO... | demo
  tests/test_protocol.py
infra/mosquitto/            config do broker do Docker (notebook)
docker-compose.yml          broker local para desenvolver sem o Pi
docs/                       mqtt-topics.md (contrato), testando-esp32.md (testes), BACKLOG.md
.github/workflows/ci.yml    lint + testes do edge e build do firmware
Makefile                    todos os comandos do dia a dia
```

## Comandos

Sempre use o Makefile; ele aponta para `edge/.venv` (o `pio` também está lá, não no PATH).

| Comando | O que faz |
|---|---|
| `make setup` | Cria `edge/.venv` com deps de dev e copia `.env` e `secrets.h` dos exemplos |
| `make setup-pi` | No Pi: instala Mosquitto e picamera2, venv com `--system-site-packages`, habilita o broker |
| `make lint` / `make test` | Ruff (check + format) e pytest do `edge/` |
| `make fw-build` | Compila o firmware (não precisa de hardware) |
| `make fw-upload` / `make fw-monitor` | Grava e lê a serial do ESP32 (precisa da placa no USB) |
| `make fw-test` | Grava o firmware de teste de montagem (env `teste`, `-DMODO_TESTE`): 12 LEDs em sequência, em repetição |
| `make broker` | Sobe o Mosquitto via Docker no notebook |
| `make monitor` / `make demo` | Assina `semaphor/<id>/#` / ciclo A/B com amarelo e vermelho geral, reenviando a cada 1 s |

**Antes de concluir qualquer mudança:** `make lint test` (Python) e `make fw-build` (firmware).
O CI roda exatamente isso.

## Contrato MQTT (resumo)

| Tópico | Direção | QoS / retained | Payload |
|---|---|---|---|
| `semaphor/<id>/cmd` | Pi → ESP32 | 1 / não | `{"roads": {"N": "green", "S": "green", "L": "red", "O": "red"}}` (vias omitidas não mudam) |
| `semaphor/<id>/state` | ESP32 → Pi | 0 / sim | `{"mode": "local" \| "remote" \| "test", "roads": {...}}` |
| `semaphor/<id>/status` | ESP32 → Pi | 1 / sim | `online` / `offline` (Last Will) |

`<id>` = `cruzamento1`. Estados: `red`, `yellow`, `green`, `off`, `flash_yellow`.
Semáforos físicos S1..S4 = vias `N`, `L`, `S`, `O`. Via **A** = N + S, via **B** = L + O.

## Regras que não podem ser quebradas

1. **O protocolo vive em três lugares.** Qualquer mudança em tópicos, vias, estados ou formato do JSON
   deve atualizar juntos: `docs/mqtt-topics.md`, `firmware/src/main.cpp` + `firmware/include/config.h`,
   e `edge/src/semaphor_edge/protocol.py` (com teste em `edge/tests/`).
2. **Resistor compartilhado.** Cada semáforo tem um único resistor para os 3 LEDs: **nunca** acenda dois
   LEDs do mesmo semáforo, nem por um instante. Toda escrita de LED passa por `showColor()`, que apaga os
   outros dois antes de acender o novo. Não escreva `digitalWrite(HIGH)` em pinos de LED fora dela
   (exceção: o modo de teste, que acende um LED por vez no total).
3. **Timeout e heartbeat.** Sem comando por `COMMAND_TIMEOUT_MS` (10 s), o ESP32 volta ao ciclo local
   (modo `local`). Todo controlador no Pi **deve reenviar o comando periodicamente** (bem abaixo de 10 s;
   o `demo` usa 1 s), mesmo sem mudança de fase. Não remova nem enfraqueça esse mecanismo.
4. **Conflito A × B.** Vias A e B nunca podem estar em verde/amarelo ao mesmo tempo. O ESP32 rejeita
   esses comandos e `protocol.build_cmd()` recusa montá-los, mas a lógica de fases do Pi (amarelo e
   vermelho geral entre trocas) é a responsável principal. Toda lógica de fases precisa de teste cobrindo isso.
5. **Segredos.** Nunca commite `firmware/include/secrets.h` nem `edge/.env`. Mudou um campo? Atualize
   os arquivos `*.example*` correspondentes.
6. **O firmware não pode bloquear.** Temporização sempre com `millis()` (máquina de estados), nunca com
   `delay()`. A única exceção é o `delay(LOOP_YIELD_MS)` (10 ms) no fim do `loop()`, que cede CPU ao Wi-Fi/TCP:
   **não remova** — sem ele o Wi-Fi demora ~30 s para conectar e o MQTT para de receber (testado).
   Wi-Fi e MQTT são não bloqueantes; a única espera é o `mqtt.connect()` quando o broker não responde.
7. **Pinos.** `setup()` põe todos os pinos em OUTPUT/LOW antes de qualquer outra coisa. Não use 1 e 3
   (Serial) nem 6–11 (flash). 0, 2 e 15 são pinos de boot: o código não pode depender do estado deles
   antes do `setup()`.
8. **Python ≥ 3.10** (notebook com 3.10, Pi OS Bookworm com 3.11). Não use sintaxe de versões mais novas.

## Como modificar (receitas)

**Mudar pinos dos LEDs:** edite `sem[4][3]` em `firmware/include/config.h` (ordem `{vermelho, amarelo, verde}`,
linhas S1..S4 = N, L, S, O) e a tabela de pinos do README. Evite 1, 3, 6–11, 12 (strapping de tensão da
flash) e 34–39 (só entrada).

**Mudar tempos do ciclo local:** `TEMPO_VERDE_MS`, `TEMPO_AMARELO_MS`, `TEMPO_VERMELHO_GERAL_MS` em `config.h`.
Se mudar, ajuste também `DEMO_CYCLE` em `cli.py` para os dois continuarem iguais.

**Novo estado de luz** (ex.: `flash_red`): adicione ao enum `LightState` e a `STATE_NAMES` em `main.cpp`,
trate em `render()` (sempre via `showColor()`), adicione a `STATES` em `protocol.py`, decida se ele conta
como ativo para o conflito (`isActive()` / `ACTIVE_STATES`) e documente em `docs/mqtt-topics.md`.

**Novo comando/tópico:** defina o tópico em `main.cpp` (assine em `updateNetwork()`, trate em `onMessage()`
filtrando por `topic`, já que hoje o callback assume que tudo é `cmd`), crie o helper em `protocol.py`,
exponha na CLI se útil e documente.

**Outro cruzamento:** troque `INTERSECTION_ID` em `config.h` (um firmware por placa) e `INTERSECTION_ID`
no `.env` do edge. Os tópicos já são separados por ID.

**Lógica nova no Pi:** crie módulos em `edge/src/semaphor_edge/`, mantenha regras de negócio puras
(sem MQTT) para serem testáveis, e use `protocol.build_cmd()` para montar mensagens.
Novos comandos de CLI vão em `cli.py` (subparser + função `cmd_*`).

**Dependências Python:** adicione em `edge/pyproject.toml`. Pacotes que dependem de hardware do Pi
(picamera2, libcamera) vêm do **apt**, não do pip.

## Testar com hardware

Tutorial completo: [docs/testando-esp32.md](docs/testando-esp32.md). Teste rápido sem a CLI:

```
mosquitto_sub -t 'semaphor/cruzamento1/#' -v
mosquitto_pub -t semaphor/cruzamento1/cmd -q 1 -m '{"roads":{"N":"green"}}'
```

O firmware loga na serial (115200): `[boot]`, `[modo] local|remote|teste`, `[wifi]`, `[mqtt]`, `[cmd] {...}`
e `[cmd] rejeitado: ...`. Enviar `t` pela serial dispara o modo de teste (12 LEDs em sequência, uma vez);
o firmware `make fw-test` repete o teste para sempre. Cada passo loga `[teste] n/12 Sx cor (GPIO y)`.
Gravar firmware sobrescreve o que está na placa; só faça isso se a tarefa pedir.

## Particularidades do ambiente

- **Maquete atual:** os 4 semáforos (12 LEDs) estão montados. Mapa de pinos no README.
- **GPIO 0** tem o LED verde do S1: se a placa não iniciar após reset (`waiting for download`), é ele
  puxando o pino para LOW no boot. Solução: mover esse LED para um pino livre (25, 26, 27, 32, 33).
- **Rede UFPI (Wi-Fi aberta):** o ESP32 só conecta em 2,4 GHz. Os IPs vêm de DHCP e **mudam**; o
  `MQTT_HOST` é compilado no firmware, então IP novo = regravar. O ESP32 **não resolve `.local`**: use IP.
- A UFPI **bloqueia SSH para o GitHub** (inclusive porta 443). Use o remoto HTTPS com token.
- Gravar no ESP32 exige o usuário no grupo `dialout`. Feche o `fw-monitor` antes de gravar.
- No Pi, o venv usa `--system-site-packages` por causa do picamera2. Não troque por venv isolado.
- Erro `Invalid publish topic`: curinga (`#`, `+`) num `mosquitto_pub`. Curingas só no `sub`.

## Estado atual

Feito e testado com hardware:

- Ambiente de desenvolvimento (Makefile, venv, PlatformIO, CI, editorconfig, extensões do VS Code).
- Firmware: Wi-Fi, MQTT com reconexão, 4 vias × 3 LEDs, publicação de `state`/`status`, Last Will,
  timeout com volta ao ciclo local.
- Firmware da nova protoboard (testado na placa em 2026-11-24 com os 4 semáforos): pinos `sem[4][3]`,
  resistor compartilhado (`showColor()`), modos `local`/`remote`/`test`, rejeição de conflito A × B,
  Wi-Fi/MQTT não bloqueantes, firmware de teste de montagem (`make fw-test`).
- Edge: config por `.env`, protocolo com validação (inclusive conflito A × B), CLI `monitor`/`set`/`demo`, testes do protocolo.
- Broker no Pi (`make setup-pi`) e ciclo completo Pi → ESP32 → Pi validado.
- Documentação: README (arquitetura), contrato MQTT, tutorial de testes do ESP32.

Ainda não verificado: o cenário de queda (`status offline` via Last Will) e o CI no GitHub.

Limitações conhecidas:

- `onMessage()` no firmware não verifica o tópico (só há um assinado hoje).
- `mqtt.connect()` pode bloquear ~alguns segundos se o broker não responder, atrasando a fase do ciclo local.
- O `demo` é um ciclo fixo; não é o controlador real.
- Broker anônimo e sem TLS.

## Próximos passos

Backlog detalhado, com prioridades, critérios de aceite e marcos: [docs/BACKLOG.md](docs/BACKLOG.md).
Resumo:

1. **Controlador de fases** (`edge/`): máquina de estados com fases N/S e L/O, amarelo e vermelho geral
   entre trocas, reenvio periódico (heartbeat) e garantia de não conflito. Começar com ciclo fixo
   (linha de base) e testes unitários com relógio injetável (sem `time.sleep` nos testes).
   Tempos ainda a definir com a equipe (o ciclo local do ESP32 usa verde 5 s, amarelo 2 s, vermelho geral 1 s).
2. **Fonte de contagem de veículos:** interface (ex.: `VehicleCounter.counts() -> dict[str, int]`) com
   implementação simulada (aleatória ou via CLI), para desenvolver o algoritmo sem câmera.
3. **Algoritmo de fila:** tempos de verde dinâmicos conforme a contagem por via, com mínimo e máximo de
   verde para não deixar via esperando para sempre. Comparar com o ciclo fixo.
4. **Serviço no Pi:** `semaphor-edge run` + unit systemd para iniciar no boot e usar o `state`/`status`
   (ex.: reagir a `offline` e a `mode: local`).
5. **Visão computacional:** captura com picamera2 e detecção de veículos (OpenCV clássico como primeiro
   passo; YOLO via NCNN depois, provavelmente com fine-tuning para os carrinhos da maquete), implementando a
   mesma interface do item 2.
6. **Qualidade:** filtro de tópico no firmware, testes do controlador e da CLI.
7. **Rede e segurança:** IP fixo (reserva na TI ou roteador do projeto); autenticação no Mosquitto se sair
   da rede de desenvolvimento.
