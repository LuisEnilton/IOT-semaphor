# Backlog

Lista do que falta para o semáforo inteligente. Atualize ao concluir ou criar tarefas (marque `[x]`).
Visão técnica e regras do código: [AGENTS.md](../AGENTS.md). Arquitetura: [README.md](../README.md).

**Prioridade:** P0 = bloqueia o resto · P1 = necessário para a entrega · P2 = melhoria.
**IDs** servem para citar em commits, PRs e issues (ex.: `E1.2`).

## Marcos

| Marco | Entrega | Itens |
|---|---|---|
| **M1. Pi no controle** | Pi roda o ciclo fixo como serviço e o ESP32 obedece | R1, E1.1–E1.4 |
| **M2. Algoritmo de fila** | Tempos de verde mudam conforme a fila (com contagem simulada) | E2, E3 |
| **M3. Visão computacional** | Contagem real pela câmera substitui a simulada | E4 |
| **M4. Demonstração** | Sistema completo inicia sozinho no boot e é apresentável | E5, E7 |

## Decisões pendentes (equipe)

- [x] **D1 (P0)** Tempos da maquete: mantidos os atuais (verde 5 s, amarelo 2 s, vermelho geral 1 s),
  podendo mudar depois. Ficam configuráveis no Pi. Algoritmo de fila: verde mínimo 3 s e máximo 15 s.
- [x] **D2 (P0)** Rede da demonstração: **Wi-Fi da UFPI**. Riscos aceitos: IPs mudam (DHCP) e a rede pode
  isolar dispositivos. Por isso R1 e R3 sobem de prioridade.
- [x] **D3 (P1)** Métrica de sucesso: **tempo médio de espera por veículo** (secundárias: fila máxima e
  veículos atendidos).
- [ ] **D4 (P2)** Contar só carros ou também tipos de veículo (influencia a escolha do detector em E4).

## Infra e rede

- [ ] **R1 (P0)** Pedir à TI da UFPI uma reserva de IP (DHCP) para o Raspberry Pi, informando o endereço
  MAC dele (`ip link show wlan0` no Pi). Hoje o `MQTT_HOST` é compilado no firmware: IP novo exige regravar o ESP32.
- [ ] **R2 (P1)** Conferir se o CI passa no GitHub (Actions): lint, testes e build do firmware.
- [ ] **R3 (P1, vira P0 se a TI negar o R1)** Permitir trocar o `MQTT_HOST` do ESP32 sem regravar
  (ex.: salvar na NVS via comando na serial, ou WiFiManager).
- [ ] **R4 (P2)** Autenticação (usuário/senha) no Mosquitto se o sistema sair da rede de desenvolvimento.

## E1. Controlador de fases no Pi (M1)

- [x] **E1.1 (P0)** Máquina de estados de fases em `edge/` (lógica pura, sem MQTT): via A verde → A amarelo →
  vermelho geral → via B verde → ... Recebe a duração do verde de fora (para o E3 plugar depois) e usa
  relógio injetável.
  *Aceite:* testes provam que A e B nunca ficam ativas juntas e que toda troca passa por amarelo e vermelho geral.
- [x] **E1.2 (P0)** Publicador MQTT: envia o estado da fase atual a cada 1 s (heartbeat, regra 3 do
  AGENTS.md), reconecta ao broker sozinho.
- [x] **E1.3 (P0)** Comando `semaphor-edge run` que liga E1.1 + E1.2 (inicialmente com ciclo fixo).
  *Aceite:* com o `run` ativo, o `state` fica em `mode: remote` e segue as fases; ao parar, o ESP32
  volta ao ciclo local em 10 s.
- [x] **E1.4 (P1)** Ler `state` e `status`: registrar em log quando o ESP32 fica `offline`, cai para
  `mode: local` ou rejeita um comando (o `state` não corresponde ao que foi enviado).
- [x] **E1.5 (P1)** Retomada segura: ao assumir o controle e quando o ESP32 volta em modo `local`
  (reboot, queda de Wi-Fi), o Pi continua pelo amarelo da via aberta, sem cortar verde.
  Testado na placa com reset no meio do ciclo.

## E2. Contagem de veículos simulada (M2)

- [x] **E2.1 (P0)** Interface `VehicleCounter` (ex.: `counts() -> dict[str, int]` por via `N`, `L`, `S`, `O`).
- [x] **E2.2 (P1)** Implementação simulada: chegadas aleatórias por via com taxa configurável e cenários
  (ex.: via A congestionada), e saída de veículos durante o verde.
- [ ] **E2.3 (P2)** Contagem manual pela CLI ou MQTT (ex.: `semaphor-edge fila N=5 L=1`) para
  demonstrações controladas.

## E3. Algoritmo de fila (M2)

- [x] **E3.1 (P0)** Verde dinâmico: verde = maior fila do grupo × 1 s por veículo, entre 3 e 15 s
  (`policy.py`). Uso na maquete: `make run-sim` (tráfego simulado).
- [x] **E3.2 (P1)** Anti-inanição: garantido pela alternância A/B. Pior caso sem verde: 21 s
  (amarelo + vermelho + verde máximo + amarelo + vermelho), mesmo com a contagem zerada. Coberto por teste.
- [x] **E3.3 (P1)** Simulação offline (`make simular`). Resultados (1800 s, média de 5 rodadas):

  | Cenário (veículos/s) | Ciclo fixo (verde 5 s) | Algoritmo de fila |
  |---|---|---|
  | A carregada: N=0,35 S=0,3 L=0,1 O=0,1 | 58,1 s de espera, fila máx. 100 | **8,7 s**, fila máx. 14 |
  | Equilibrado leve: 0,1 em todas | 5,9 s | 5,8 s |
  | Equilibrado pesado: 0,25 em todas | 12,0 s | **9,1 s** |

  No cenário desbalanceado o ciclo fixo não dá vazão à via A (capacidade de ~0,31 veículo/s) e a fila cresce
  sem parar. Com tráfego leve os dois empatam. Modelo simples (chegadas aleatórias, 1 veículo/s no verde);
  os números servem para comparar métodos, não para prever tráfego real.
- [ ] **E3.4 (P2)** Pular a fase da via vazia (só abre se houver demanda), respeitando o anti-inanição.

## E4. Visão computacional (M3)

- [ ] **E4.1 (P0)** Captura com picamera2 no Pi e calibração das regiões de interesse (ROI) de cada via
  na imagem da maquete (arquivo de configuração, não fixo no código).
- [ ] **E4.2 (P1)** Detector clássico com OpenCV (subtração de fundo + contornos por ROI) implementando
  `VehicleCounter`. Primeira versão funcional.
- [ ] **E4.3 (P1)** Avaliar precisão e FPS do detector na maquete (iluminação real da apresentação).
- [ ] **E4.4 (P2)** Dataset com fotos dos carrinhos e fine-tuning de YOLO exportado para NCNN, se o
  detector clássico não for suficiente (decisão a partir de E4.3).
- [ ] **E4.5 (P2)** Visualização de debug: imagem com ROIs e contagens desenhadas (para ajustar e para a demo).

## E5. Implantação no Pi (M4)

- [ ] **E5.1 (P1)** Unit systemd para o `semaphor-edge run` (inicia no boot, reinicia se cair) e
  `make install-service`.
- [ ] **E5.2 (P1)** Logs úteis (fase atual, contagens, decisões do algoritmo) via journald.
- [ ] **E5.3 (P2)** Roteiro de "liga tudo" para o dia da apresentação (ordem de energização, checagens rápidas).

## E6. Firmware (melhorias)

- [ ] **E6.1 (P1)** Testar o Last Will: desligar o ESP32 e conferir `status offline` no broker.
- [ ] **E6.2 (P1)** Confirmar o boot após desligar e religar a alimentação, com o LED no GPIO 0
  (até agora só foi testado o reset pela USB).
- [ ] **E6.3 (P2)** Filtrar o tópico em `onMessage()` antes de tratar como `cmd`.
- [ ] **E6.4 (P2)** Reduzir o bloqueio do `mqtt.connect()` quando o broker não responde (hoje atrasa o
  ciclo local em alguns segundos).

## E7. Qualidade e documentação

- [ ] **E7.1 (P1)** Testes da CLI e do controlador (E1) rodando no CI.
- [ ] **E7.2 (P1)** Atualizar README/AGENTS a cada marco (estado atual, como rodar).
- [ ] **E7.3 (P2)** Painel simples (web ou terminal) com fase atual, filas e estado do ESP32, para a apresentação.
- [ ] **E7.4 (P2)** Material do relatório: diagrama de arquitetura, resultados de E3.3 e E4.3.

## Concluído

- [x] Ambiente de desenvolvimento (Makefile, venv, PlatformIO, CI, VS Code) e repositório no GitHub
- [x] Contrato MQTT (`cmd`, `state`, `status`) e CLI `monitor`/`set`
- [x] E1: controlador de fases no Pi (`semaphor-edge run` / `make run`)
- [x] Broker Mosquitto no Pi e comunicação Pi ↔ ESP32 validada
- [x] Firmware dos 4 semáforos: resistor compartilhado, modos local/remote/test, rejeição de conflito A × B,
  timeout com volta ao ciclo local, firmware de teste de montagem
- [x] Documentação: arquitetura (README), AGENTS.md, tutorial de testes do ESP32
