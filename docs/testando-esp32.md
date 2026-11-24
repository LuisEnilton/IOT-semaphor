# Testando o ESP32 pelo notebook

Tutorial para validar o semáforo (ESP32 ligado por USB ao notebook) sem precisar do Raspberry Pi
para a lógica. Para a arquitetura, veja o [README](../README.md); para o formato das mensagens,
[mqtt-topics.md](mqtt-topics.md).

> Na maquete atual, só a via **N** tem LEDs montados: vermelho = GPIO 16, amarelo = 17, verde = 18.
> Os comandos para as outras vias funcionam, mas você só enxerga o resultado no tópico `state`.

## 0. Pré-requisitos (uma vez)

```
make setup                                  # venv, edge/.env e firmware/include/secrets.h
sudo usermod -aG dialout $USER              # permissão na porta serial; reabra a sessão depois
ls /dev/ttyUSB0                             # a placa deve aparecer (pode ser /dev/ttyACM0)
```

Edite `firmware/include/secrets.h`:

| Campo | Valor |
|---|---|
| `WIFI_SSID`, `WIFI_PASS` | Rede 2,4 GHz (na UFPI: `UFPI`, senha vazia) |
| `MQTT_HOST` | **IP** do broker (veja a seção 3), não `.local` |

Use um cabo USB **de dados** (alguns só carregam) e feche qualquer monitor serial aberto antes de gravar.

## 1. Gravar o firmware

```
make fw-build       # compila (a 1ª vez baixa o toolchain, ~1-2 min)
make fw-upload      # grava no ESP32
```

Esperado: `Hash of data verified` e `[SUCCESS]`.
Se der `Failed to connect`, segure o botão **BOOT** da placa quando aparecer `Connecting...`.

## 2. Teste sem rede: serial e LED

```
make fw-monitor     # Ctrl+C para sair
```

Pressione o botão **EN** (reset) e confira:

```
[boot] semaforo cruzamento1
[safe] modo seguro: amarelo piscante
[wifi] conectando a UFPI...
[mqtt] conectado               # só aparece se o broker estiver acessível
```

**LED:** o amarelo (GPIO 17) deve piscar ~2x por segundo, com vermelho e verde apagados.
Isso é o modo seguro e prova que a placa, o firmware e a fiação do LED estão ok.

## 3. Teste de comunicação (MQTT)

O ESP32 precisa de um broker. Escolha **um**:

| | A. Broker no notebook | B. Broker no Raspberry Pi |
|---|---|---|
| Quando usar | Pi indisponível | Cenário real do projeto |
| `MQTT_HOST` no `secrets.h` | IP do notebook (`ip -4 -br addr`) | IP do Pi (`hostname -I` no Pi) |
| Subir o broker | `make broker` | já roda no Pi |
| `MQTT_HOST` no `edge/.env` | `localhost` | IP do Pi |

Depois de mudar o `secrets.h`, grave de novo (`make fw-upload`). Pare o outro broker para
não ficar com dois ativos (`docker compose down` no notebook).

### 3.1 Observar

Num terminal:

```
make monitor
```

Ao reiniciar o ESP32 devem aparecer `status online` e um `state` com `"safe_mode":true`.
Como são mensagens *retained*, elas aparecem também se o ESP32 já estava ligado.

### 3.2 Comandar

Em outro terminal:

```
edge/.venv/bin/semaphor-edge set N=red
edge/.venv/bin/semaphor-edge set N=yellow
edge/.venv/bin/semaphor-edge set N=green
edge/.venv/bin/semaphor-edge set N=green S=green L=red O=red     # as 4 vias
```

Esperado a cada comando: o LED muda, o `make monitor` mostra o `cmd` e o novo `state`
(`"safe_mode":false`), e o log serial mostra `[cmd] {...}`.

Estados válidos: `red`, `yellow`, `green`, `off`, `flash_yellow`. Vias: `N`, `L`, `S`, `O`.

### 3.3 Ciclo contínuo

```
make demo           # alterna N/S e L/O (Ctrl+C para parar)
```

## 4. Teste do modo seguro (timeout)

1. Com o ESP32 em `green`, pare de mandar comandos.
2. Após **10 s** o LED volta a piscar amarelo e o `state` mostra `"safe_mode":true`.

Esse é o comportamento protetor se o Pi travar ou a rede cair.

## 5. Teste de queda (Last Will)

Com `make monitor` aberto, desconecte o USB (ou o 3V3/GND) do ESP32. Em até ~15 s o broker
publica `status offline`. Ao religar, volta `status online`.

## Checklist rápido

- [ ] Gravou sem erro
- [ ] Serial mostra `[boot]` e `[safe]`
- [ ] LED amarelo piscando (modo seguro)
- [ ] `[wifi]` conecta e `[mqtt] conectado` aparece
- [ ] `status online` no `make monitor`
- [ ] `set N=red/yellow/green` muda o LED e o `state`
- [ ] Sem comandos por 10 s volta ao amarelo piscante
- [ ] Desligar o ESP32 gera `status offline`

## Problemas comuns

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `Permission denied: /dev/ttyUSB0` | Usuário fora do grupo `dialout` | `sudo usermod -aG dialout $USER` e reabra a sessão |
| Porta não aparece | Cabo só de carga ou driver | Troque o cabo; `dmesg \| tail` |
| `Failed to connect to ESP32` | Placa não entrou em modo de gravação | Segure **BOOT** durante o `Connecting...` |
| `Could not open port` / ocupada | Monitor serial aberto | Feche o `make fw-monitor` antes de gravar |
| `[wifi]` repete sem conectar | Rede 5 GHz, SSID/senha errados | Use 2,4 GHz e confira o `secrets.h` |
| Wi-Fi ok, mas sem `[mqtt] conectado` | `MQTT_HOST` errado, broker parado ou rede isolando clientes | Confira o IP e o broker (`mosquitto_pub -t t -m x`); na UFPI teste com hotspot |
| `Invalid publish topic` | Curinga `#` ou `+` num `mosquitto_pub` | Publique em `semaphor/cruzamento1/cmd`, sem curinga |
| Comando aceito, LED não muda | Fiação/pino | Veja se o `state` mudou; confira o GPIO e o resistor do LED |
| Tudo funcionava e parou | IP do broker mudou (DHCP) | Atualize `MQTT_HOST` e grave de novo |
