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
  include/config.h          ID do cruzamento, pinos dos LEDs, timeout do modo seguro
  include/secrets.example.h modelo de Wi-Fi/broker (secrets.h é local e ignorado pelo git)
  src/main.cpp              Wi-Fi, MQTT, renderização dos LEDs, modo seguro
edge/
  pyproject.toml            pacote semaphor-edge (paho-mqtt); extras dev: pytest, ruff, platformio
  .env.example              MQTT_HOST, MQTT_PORT, INTERSECTION_ID (.env é local)
  src/semaphor_edge/
    config.py               lê .env + variáveis de ambiente
    protocol.py             ROADS, STATES, topic(), build_cmd() com validação
    cli.py                  semaphor-edge monitor | set VIA=ESTADO... | demo
  tests/test_protocol.py
infra/mosquitto/            config do broker do Docker (notebook)
docker-compose.yml          broker local para desenvolver sem o Pi
docs/                       mqtt-topics.md (contrato), testando-esp32.md (tutorial de testes)
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
| `make broker` | Sobe o Mosquitto via Docker no notebook |
| `make monitor` / `make demo` | Assina `semaphor/<id>/#` / alterna N-S e L-O a cada 4 s |

**Antes de concluir qualquer mudança:** `make lint test` (Python) e `make fw-build` (firmware).
O CI roda exatamente isso.

## Contrato MQTT (resumo)

| Tópico | Direção | QoS / retained | Payload |
|---|---|---|---|
| `semaphor/<id>/cmd` | Pi → ESP32 | 1 / não | `{"roads": {"N": "green", "S": "green", "L": "red", "O": "red"}}` (vias omitidas não mudam) |
| `semaphor/<id>/state` | ESP32 → Pi | 0 / sim | `{"safe_mode": false, "roads": {...}}` |
| `semaphor/<id>/status` | ESP32 → Pi | 1 / sim | `online` / `offline` (Last Will) |

`<id>` = `cruzamento1`. Estados: `red`, `yellow`, `green`, `off`, `flash_yellow`.

## Regras que não podem ser quebradas

1. **O protocolo vive em três lugares.** Qualquer mudança em tópicos, vias, estados ou formato do JSON
   deve atualizar juntos: `docs/mqtt-topics.md`, `firmware/src/main.cpp` + `firmware/include/config.h`,
   e `edge/src/semaphor_edge/protocol.py` (com teste em `edge/tests/`).
2. **Modo seguro.** Sem comando por `COMMAND_TIMEOUT_MS` (10 s), o ESP32 pisca amarelo em todas as vias.
   Todo controlador no Pi **deve reenviar o comando periodicamente** (bem abaixo de 10 s; o `demo` usa 2 s),
   mesmo sem mudança de fase. Não remova nem enfraqueça esse mecanismo.
3. **O ESP32 não valida conflitos.** Quem garante que vias cruzadas (N/S × L/O) nunca ficam verdes ao
   mesmo tempo é o código do Pi. Toda lógica de fases precisa de teste cobrindo isso.
4. **Segredos.** Nunca commite `firmware/include/secrets.h` nem `edge/.env`. Mudou um campo? Atualize
   os arquivos `*.example*` correspondentes.
5. **O firmware não pode bloquear.** Nada de `delay()` longo no `loop()`; a renderização (pisca-pisca) e o
   `mqtt.loop()` precisam rodar continuamente.
6. **Python ≥ 3.10** (notebook com 3.10, Pi OS Bookworm com 3.11). Não use sintaxe de versões mais novas.

## Como modificar (receitas)

**Mudar pinos dos LEDs:** edite `LED_PINS` em `firmware/include/config.h` (ordem `{vermelho, amarelo, verde}`
por via, vias na ordem N, L, S, O). Evite GPIOs 0, 2, 12, 15 (strapping) e 34–39 (só entrada).

**Novo estado de luz** (ex.: `flash_red`): adicione ao enum `LightState` e a `STATE_NAMES` em `main.cpp`,
trate em `render()`, ajuste o laço `k < 5` em `onMessage()` para o novo total, adicione a `STATES` em
`protocol.py` e documente em `docs/mqtt-topics.md`.

**Novo comando/tópico:** defina o tópico em `main.cpp` (assine em `connectMqtt()`, trate em `onMessage()`
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

O firmware loga na serial (115200): `[boot]`, `[safe]`, `[wifi]`, `[mqtt] conectado`, `[cmd] {...}`.
Gravar firmware sobrescreve o que está na placa; só faça isso se a tarefa pedir.

## Particularidades do ambiente

- **Maquete atual:** só a via **N** tem LEDs montados (GPIO 16, 17, 18). As outras vias só aparecem no `state`.
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
  modo seguro por timeout.
- Edge: config por `.env`, protocolo com validação, CLI `monitor`/`set`/`demo`, testes do protocolo.
- Broker no Pi (`make setup-pi`) e ciclo completo Pi → ESP32 → Pi validado.
- Documentação: README (arquitetura), contrato MQTT, tutorial de testes do ESP32.

Ainda não verificado: o cenário de queda (`status offline` via Last Will) e o CI no GitHub.

Limitações conhecidas:

- `semaphor-edge set` com valor inválido imprime traceback em vez de mensagem amigável.
- `onMessage()` no firmware não verifica o tópico (só há um assinado hoje).
- O `demo` é um ciclo fixo sem amarelo nem vermelho geral; não é o controlador real.
- Broker anônimo e sem TLS.

## Próximos passos

1. **Controlador de fases** (`edge/`): máquina de estados com fases N/S e L/O, amarelo e vermelho geral
   entre trocas, reenvio periódico (heartbeat) e garantia de não conflito. Começar com ciclo fixo
   (linha de base) e testes unitários com relógio injetável (sem `time.sleep` nos testes).
   Tempos de amarelo e vermelho geral ainda a definir com a equipe (sugestão: 3 s e 1 s).
2. **Fonte de contagem de veículos:** interface (ex.: `VehicleCounter.counts() -> dict[str, int]`) com
   implementação simulada (aleatória ou via CLI), para desenvolver o algoritmo sem câmera.
3. **Algoritmo de fila:** tempos de verde dinâmicos conforme a contagem por via, com mínimo e máximo de
   verde para não deixar via esperando para sempre. Comparar com o ciclo fixo.
4. **Serviço no Pi:** `semaphor-edge run` + unit systemd para iniciar no boot e usar o `state`/`status`
   (ex.: reagir a `offline` e a `safe_mode`).
5. **Visão computacional:** captura com picamera2 e detecção de veículos (OpenCV clássico como primeiro
   passo; YOLO via NCNN depois, provavelmente com fine-tuning para os carrinhos da maquete), implementando a
   mesma interface do item 2.
6. **Qualidade:** mensagem de erro amigável na CLI, filtro de tópico no firmware, testes do controlador
   e da CLI.
7. **Rede e segurança:** IP fixo (reserva na TI ou roteador do projeto); autenticação no Mosquitto se sair
   da rede de desenvolvimento.
