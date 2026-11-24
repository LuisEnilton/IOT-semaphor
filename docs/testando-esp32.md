# Testando o ESP32 pelo notebook

Tutorial para validar o semáforo (ESP32 ligado por USB ao notebook) sem precisar do Raspberry Pi
para a lógica. Para a arquitetura, veja o [README](../README.md); para o formato das mensagens,
[mqtt-topics.md](mqtt-topics.md).

> Na maquete atual estão montados **S1** (via `N`: vermelho 15, amarelo 2, verde 0) e **S2** (via `L`:
> vermelho 4, amarelo 16, verde 17). S3 (`S`) e S4 (`O`) aparecem só no tópico `state`.
> Mapa completo de pinos no [README](../README.md#hardware-da-maquete).

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

## 2. Teste sem rede: serial e LEDs

```
make fw-monitor     # Ctrl+C para sair
```

Pressione o botão **EN** (reset) e confira:

```
[boot] semaforo cruzamento1 (envie 't' para o modo de teste)
[wifi] conectando a UFPI...
[modo] local: ciclo fixo
[wifi] conectado, IP 10.13.x.x
[mqtt] conectado               # só aparece se o broker estiver acessível
```

**Ciclo local:** sem o Pi, os LEDs seguem o ciclo fixo: S1 verde 5 s → S1 amarelo 2 s → todos
vermelhos 1 s → S2 verde 5 s → S2 amarelo 2 s → todos vermelhos 1 s. Nunca deve haver dois LEDs
acesos no mesmo semáforo, nem S1 e S2 fora do vermelho ao mesmo tempo.

**Modo de teste (fiação):** com o `make fw-monitor` aberto, digite `t`. Os 12 LEDs acendem um por vez,
500 ms cada, na ordem S1 vermelho/amarelo/verde, S2..., e depois volta o ciclo local. Use isso para
achar LED invertido, pino trocado ou solda ruim.

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

Ao reiniciar o ESP32 devem aparecer `status online` e um `state` com `"mode":"local"`.
Como são mensagens *retained*, elas aparecem também se o ESP32 já estava ligado.

### 3.2 Comandar

Em outro terminal:

```
edge/.venv/bin/semaphor-edge set N=red S=red L=red O=red        # tudo vermelho
edge/.venv/bin/semaphor-edge set N=green S=green                # via A verde (S1)
edge/.venv/bin/semaphor-edge set N=yellow S=yellow
edge/.venv/bin/semaphor-edge set N=red S=red L=green O=green    # via B verde (S2)
```

Esperado a cada comando: o LED muda, o `make monitor` mostra o `cmd` e o novo `state`
(`"mode":"remote"`), e o log serial mostra `[cmd] {...}`. Mande o próximo comando em menos de
10 s, senão o ESP32 volta ao ciclo local.

**Conflito:** `semaphor-edge set N=green L=green` é recusado pela própria CLI. Para testar a
proteção do ESP32, publique direto:

```
mosquitto_pub -t semaphor/cruzamento1/cmd -m '{"roads":{"N":"green","L":"green"}}'
```

O serial deve mostrar `[cmd] rejeitado: vias A e B ativas ao mesmo tempo` e os LEDs não mudam.
Atenção: vias omitidas mantêm o estado atual, então `set N=green` sozinho é rejeitado se a via B
estiver aberta naquele momento.

Estados válidos: `red`, `yellow`, `green`, `off`, `flash_yellow`. Vias: `N`, `L`, `S`, `O`.

### 3.3 Ciclo contínuo

```
make demo           # mesmo ciclo do modo local, mas comandado pelo Pi/notebook (Ctrl+C para parar)
```

## 4. Teste do timeout (volta ao ciclo local)

1. Mande `set N=green S=green L=red O=red` e pare de mandar comandos.
2. Após **10 s** o S1 passa para amarelo (2 s), depois todos vermelhos, e o ciclo local recomeça.
   O `state` mostra `"mode":"local"`.

Esse é o comportamento protetor se o Pi travar ou a rede cair.

## 5. Teste de queda (Last Will)

Com `make monitor` aberto, desconecte o USB (ou o 3V3/GND) do ESP32. Em até ~15 s o broker
publica `status offline`. Ao religar, volta `status online`.

## Checklist rápido

- [ ] Gravou sem erro
- [ ] Serial mostra `[boot]` e `[modo] local`
- [ ] Ciclo local correto, nunca 2 LEDs acesos no mesmo semáforo
- [ ] Modo de teste (`t`) acende os LEDs montados na ordem certa
- [ ] `[wifi]` conecta e `[mqtt] conectado` aparece
- [ ] `status online` no `make monitor`
- [ ] `set` muda os LEDs e o `state` (`mode: remote`)
- [ ] Comando com conflito A/B é rejeitado
- [ ] Sem comandos por 10 s volta ao ciclo local
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
| Ao ligar, nada acontece; serial mostra `waiting for download` | GPIO 0 (verde do S1) puxado para LOW pelo LED no boot | Veja a nota sobre pinos de boot no README; teste reiniciando com o LED desconectado |
| Gravação falha só com os LEDs montados | GPIO 2 ou 0 com carga durante a gravação | Segure **BOOT**; se persistir, desconecte o S1 para gravar |
