# Semáforo inteligente (IoT)

Maquete de cruzamento com 4 vias. **ESP32** controla os LEDs; **Raspberry Pi 5** roda o algoritmo de fila
(e, futuramente, visão computacional). Comunicação por **MQTT** — contrato em [docs/mqtt-topics.md](docs/mqtt-topics.md).

```
firmware/  PlatformIO (ESP32)          edge/   Python (Raspberry Pi)
infra/     config do Mosquitto         docs/   documentação
```

## Arquitetura

### Visão geral

```
                         Rede Wi-Fi (UFPI)
 ┌──────────────────────────────────────────────────────────┐
 │                                                          │
 │   ┌────────────────────────────┐        ┌─────────────┐  │
 │   │  Raspberry Pi 5            │        │   ESP32     │  │
 │   │                            │        │             │  │
 │   │  câmera ─► visão (futuro)  │        │  firmware/  │  │
 │   │              │ contagem    │        │  (Arduino)  │  │
 │   │              ▼ por via     │  cmd   │      │      │  │
 │   │  algoritmo de fila (edge/) ├───────►│      ▼      │  │
 │   │              │             │        │  LEDs (4×3) │  │
 │   │              ▼             │ state  │             │  │
 │   │  cliente MQTT ◄────────────┼────────┤  status     │  │
 │   │       ▲  ▼                 │ status │             │  │
 │   │  ┌────┴──────────┐         │        └──────┬──────┘  │
 │   │  │ Mosquitto     │◄────────┼───────────────┘         │
 │   │  │ (broker :1883)│         │   (o ESP32 é cliente    │
 │   │  └───────────────┘         │    MQTT do broker do Pi)│
 │   └────────────────────────────┘                         │
 └──────────────────────────────────────────────────────────┘
```

| Componente | Papel | Código |
|---|---|---|
| **Raspberry Pi 5** | Decide. Conta veículos, calcula as fases do semáforo e manda os comandos. Hospeda o broker | `edge/` |
| **ESP32** | Executa. Acende os LEDs conforme o comando recebido e informa seu estado | `firmware/` |
| **Mosquitto** | Intermediário (broker MQTT) entre os dois. Roda no Pi, porta 1883 | `infra/` |

A separação é intencional: o **Pi pensa** e o **ESP32 só obedece**. O ESP32 não conhece
a lógica de tráfego, então dá para trocar o algoritmo sem regravar o firmware.

### Como a comunicação funciona

Os dois lados **não se falam diretamente**. Cada um é cliente do broker MQTT e se comunica por
**tópicos** (publicar/assinar):

```
 Pi (edge/)                      Mosquitto                       ESP32
     │  publica cmd                  │                              │
     ├──────────────────────────────►│  entrega a quem assina cmd   │
     │  semaphor/<id>/cmd            ├─────────────────────────────►│ liga/desliga LEDs
     │                               │                              │
     │                               │  publica state (retained)    │
     │  recebe state                 │◄─────────────────────────────┤ semaphor/<id>/state
     │◄──────────────────────────────┤                              │
     │                               │  publica status (retained)   │
     │  recebe status                │◄─────────────────────────────┤ online / offline
     │◄──────────────────────────────┤                              │
```

| Tópico | Quem publica | Para quê |
|---|---|---|
| `semaphor/<id>/cmd` | Pi | Estado desejado das vias, ex.: `{"roads":{"N":"green","S":"green","L":"red","O":"red"}}` |
| `semaphor/<id>/state` | ESP32 | Estado real dos LEDs, publicado a cada mudança (*retained*) |
| `semaphor/<id>/status` | ESP32 | `online` ao conectar; `offline` publicado pelo broker se o ESP32 cair (*Last Will*) |

Detalhes e formatos completos em [docs/mqtt-topics.md](docs/mqtt-topics.md).

### Por que MQTT

- **Desacoplamento:** o Pi não precisa saber o IP do ESP32, só do broker. O ESP32 reconecta sozinho.
- **Retained:** quem conecta depois (por exemplo, uma ferramenta de monitoramento) já recebe o último `state` e `status`.
- **Last Will:** o Pi sabe se o semáforo caiu sem precisar fazer polling.
- **Escala:** outro cruzamento é só outro `<id>` nos tópicos, e dá para depurar com `mosquitto_sub`.

### Ciclo de uma troca de fase

1. O algoritmo (Pi) decide abrir a via A (N/S) e fechar a via B (L/O).
2. O cliente MQTT publica o JSON em `semaphor/cruzamento1/cmd` (QoS 1).
3. O broker entrega ao ESP32, que valida o comando (sem conflito entre A e B) e atualiza as 4 vias e os 12 LEDs.
4. O ESP32 publica o novo `state`; o Pi confere se o semáforo fez o que foi pedido e avisa no log se não.
5. O Pi **reenvia o comando a cada 1 s** (heartbeat), mesmo sem mudança.

Quem faz isso é o controlador de fases (`make run` / `semaphor-edge run`, código em `edge/src/semaphor_edge/`
`phases.py` e `runner.py`). Os tempos vêm do `edge/.env` (`GREEN_S`, `YELLOW_S`, `ALL_RED_S`) ou das opções
`--green`, `--yellow` e `--all-red`. Ao assumir o controle, e sempre que o ESP32 volta em modo `local`
(reboot, queda de Wi-Fi), o Pi retoma pelo amarelo da via que estiver aberta, para nunca cortar um verde.

### Algoritmo de fila

Com `make run-sim`, o Pi usa o **verde dinâmico**: ao abrir uma via, dá tempo para escoar a maior fila dela
(fila × 1 s por veículo), entre **3 e 15 s**. Como as vias A e B continuam se alternando, nenhuma fica mais de
21 s sem verde. Por enquanto as filas vêm de um **tráfego simulado** (`ARRIVALS` no `edge/.env`); a câmera
(visão computacional) vai fornecer a contagem real pela mesma interface (`VehicleCounter`).

`make simular` compara o ciclo fixo com o algoritmo em tempo simulado, pelo **tempo médio de espera por
veículo**. No cenário com a via A mais carregada, a espera cai de ~58 s para ~9 s (detalhes em
[docs/BACKLOG.md](docs/BACKLOG.md), item E3.3).

### Hardware da maquete

ESP32 DevKit 38 pinos, 4 semáforos com 3 LEDs cada (ativos em HIGH). Cada semáforo tem **um resistor
compartilhado** pelos 3 LEDs, então o firmware nunca acende dois LEDs do mesmo semáforo ao mesmo tempo.

| Semáforo | Via MQTT | Grupo | Vermelho | Amarelo | Verde |
|---|---|---|---|---|---|
| S1 | `N` | A | 15 | 2 | 0 |
| S2 | `L` | B | 4 | 16 | 17 |
| S3 | `S` | A | 5 | 18 | 19 |
| S4 | `O` | B | 21 | 22 | 23 |

Os 4 semáforos estão montados. Os pinos ficam em `sem[4][3]` em `firmware/include/config.h`.
Algumas placas ESP32 têm um LED azul ligado ao GPIO 2 (amarelo do S1); a placa da maquete não tem.

> **Pinos de boot (0, 2, 15):** o firmware os coloca em LOW logo no início do `setup()`, mas antes
> disso quem manda é o hardware. O **GPIO 0 precisa estar em HIGH no reset** para a placa iniciar o
> programa; com um LED + resistor até o GND nele (verde do S1), ele pode ser puxado para baixo e a
> placa ficar parada em modo de gravação (`waiting for download` na serial). Se isso acontecer, troque
> o verde do S1 para um pino livre (ex.: 25, 26, 27, 32 ou 33) e atualize `sem[][]`. O GPIO 15 em LOW no
> boot só silencia o log inicial da ROM.

### Modos do ESP32 e segurança

| Modo | Quando | O que faz |
|---|---|---|
| `local` | Ao ligar e sempre que o Pi fica **10 s sem mandar comando** | Ciclo fixo: A verde 5 s → A amarelo 2 s → vermelho geral 1 s → B verde 5 s → B amarelo 2 s → vermelho geral 1 s |
| `remote` | Ao receber um comando válido do Pi | Segue os comandos |
| `test` | Ao receber `t` pela serial, ou sempre no firmware de teste (`make fw-test`) | Acende os 12 LEDs, um por vez, 500 ms cada, informando semáforo, cor e GPIO na serial |

Assim o cruzamento continua funcionando se o Pi travar ou a rede cair. Por isso o passo 5 acima é
obrigatório: o comando funciona como um *heartbeat*. Os tempos do ciclo local ficam em `config.h`.

O ESP32 **rejeita comandos que abririam as vias A e B ao mesmo tempo** (verde/amarelo nas duas), como
última barreira. A lógica de fases (amarelo e vermelho geral entre as trocas) continua sendo do Pi.

### Rede

- ESP32, Pi e notebook devem estar na **mesma rede** (hoje, a Wi-Fi da UFPI, que é aberta).
  O ESP32 só conecta em **2,4 GHz**.
- O ESP32 usa o **IP** do Pi (`MQTT_HOST` em `firmware/include/secrets.h`), não `raspberrypi.local`:
  ele normalmente não resolve nomes `.local`. O IP vem de DHCP, então se mudar é preciso gravar o firmware de novo.
- Redes institucionais podem **isolar clientes** (um dispositivo não enxerga o outro) e **bloquear SSH**
  para o GitHub; neste caso, use HTTPS para o git e, se o isolamento atrapalhar, um roteador/hotspot só do projeto.
- O broker de desenvolvimento é **anônimo e sem TLS**: use só em rede local confiável.

## Setup (colaboradores)

Pré-requisitos no notebook: Python ≥ 3.10, VS Code (instale as extensões recomendadas), Docker (opcional).

1. `make setup` — cria `edge/.venv`, `edge/.env` e `firmware/include/secrets.h`.
2. Edite `firmware/include/secrets.h` com o Wi-Fi e o IP/hostname do broker (**nunca commite**).
3. Broker: no Pi use `make setup-pi` (uma vez). Sem o Pi, use `make broker` (Docker) e aponte `MQTT_HOST` para o seu IP.
4. Firmware: `make fw-build` → `make fw-upload` (ESP32 via USB) → `make fw-monitor`.
   Para conferir a montagem dos LEDs: `make fw-test` (firmware de teste) e depois `make fw-upload` para voltar ao normal.
   Se o upload falhar por permissão: `sudo usermod -aG dialout $USER` e reabra a sessão.
5. Teste ponta a ponta: `make monitor` num terminal e `make run` (controlador de fases) em outro (ou
   `edge/.venv/bin/semaphor-edge set N=green S=green L=red O=red`).

> Guia completo de testes do ESP32 pelo notebook (serial, LEDs, MQTT, modos):
> [docs/testando-esp32.md](docs/testando-esp32.md).

### Raspberry Pi
Pi OS 64-bit. Clone o repo, rode `make setup-pi`. Para desenvolver nele, use **VS Code Remote-SSH**
(`ssh <usuario>@raspberrypi.local`). Ele usa venv com `--system-site-packages` porque o `picamera2`
vem do apt.

## Fluxo de trabalho
- Branch por funcionalidade + Pull Request; o CI roda lint, testes e build do firmware.
- Mudou o protocolo? Atualize `docs/mqtt-topics.md`, `firmware/` e `edge/protocol.py` juntos.
- Antes de commitar: `make lint test`.
