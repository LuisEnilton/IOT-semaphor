# Backlog

Lista do que falta para o semáforo inteligente. Atualize ao concluir ou criar tarefas (marque `[x]`).
Visão técnica e regras do código: [AGENTS.md](../AGENTS.md). Arquitetura: [README.md](../README.md).

**Prioridade:** P0 = bloqueia o resto · P1 = necessário para a entrega · P2 = melhoria.
**IDs** servem para citar em commits, PRs e issues (ex.: `E1.2`).

## Marcos

| Marco | Entrega | Itens |
|---|---|---|
| **M1. Pi no controle** | Pi roda o ciclo fixo como serviço e o ESP32 obedece | D1–D2, R1, E1.1–E1.4 |
| **M2. Algoritmo de fila** | Tempos de verde mudam conforme a fila (com contagem simulada) | E2, E3 |
| **M3. Visão computacional** | Contagem real pela câmera substitui a simulada | E4 |
| **M4. Demonstração** | Sistema completo inicia sozinho no boot e é apresentável | E5, E7 |

## Decisões pendentes (equipe)

- [ ] **D1 (P0)** Tempos da maquete: amarelo e vermelho geral, e verde mínimo e máximo para o algoritmo.
  Hoje o ciclo local do ESP32 usa verde 5 s, amarelo 2 s e vermelho geral 1 s.
- [ ] **D2 (P0)** Rede da demonstração: continuar na Wi-Fi da UFPI (IPs mudam, risco de isolamento entre
  dispositivos) ou usar um roteador/hotspot próprio do projeto. Afeta R1.
- [ ] **D3 (P1)** Métrica de sucesso do algoritmo (ex.: tempo médio de espera, fila máxima, veículos
  atendidos por ciclo) para comparar com o ciclo fixo.
- [ ] **D4 (P2)** Contar só carros ou também tipos de veículo (influencia a escolha do detector em E4).

## Infra e rede

- [ ] **R1 (P0)** IP fixo para o Raspberry Pi (reserva na TI ou no roteador do projeto, conforme D2).
  Hoje o `MQTT_HOST` é compilado no firmware: IP novo exige regravar o ESP32.
- [ ] **R2 (P1)** Conferir se o CI passa no GitHub (Actions): lint, testes e build do firmware.
- [ ] **R3 (P2)** Permitir trocar o `MQTT_HOST` do ESP32 sem regravar (ex.: salvar na NVS via comando
  na serial, ou WiFiManager).
- [ ] **R4 (P2)** Autenticação (usuário/senha) no Mosquitto se o sistema sair da rede de desenvolvimento.

## E1. Controlador de fases no Pi (M1)

- [ ] **E1.1 (P0)** Máquina de estados de fases em `edge/` (lógica pura, sem MQTT): via A verde → A amarelo →
  vermelho geral → via B verde → ... Recebe a duração do verde de fora (para o E3 plugar depois) e usa
  relógio injetável.
  *Aceite:* testes provam que A e B nunca ficam ativas juntas e que toda troca passa por amarelo e vermelho geral.
- [ ] **E1.2 (P0)** Publicador MQTT: envia o estado da fase atual a cada 1 s (heartbeat, regra 3 do
  AGENTS.md), reconecta ao broker sozinho.
- [ ] **E1.3 (P0)** Comando `semaphor-edge run` que liga E1.1 + E1.2 (inicialmente com ciclo fixo).
  *Aceite:* com o `run` ativo, o `state` fica em `mode: remote` e segue as fases; ao parar, o ESP32
  volta ao ciclo local em 10 s.
- [ ] **E1.4 (P1)** Ler `state` e `status`: registrar em log quando o ESP32 fica `offline`, cai para
  `mode: local` ou rejeita um comando (o `state` não corresponde ao que foi enviado).

## E2. Contagem de veículos simulada (M2)

- [ ] **E2.1 (P0)** Interface `VehicleCounter` (ex.: `counts() -> dict[str, int]` por via `N`, `L`, `S`, `O`).
- [ ] **E2.2 (P1)** Implementação simulada: chegadas aleatórias por via com taxa configurável e cenários
  (ex.: via A congestionada), e saída de veículos durante o verde.
- [ ] **E2.3 (P2)** Contagem manual pela CLI ou MQTT (ex.: `semaphor-edge fila N=5 L=1`) para
  demonstrações controladas.

## E3. Algoritmo de fila (M2)

- [ ] **E3.1 (P0)** Verde dinâmico: duração do verde de cada via proporcional à fila, limitada por verde
  mínimo e máximo (D1). *Aceite:* testes com filas desbalanceadas dão mais verde à via mais cheia.
- [ ] **E3.2 (P1)** Anti-inanição: nenhuma via espera mais que um limite, mesmo com fila zero na contagem
  (proteção contra falha de detecção).
- [ ] **E3.3 (P1)** Simulação offline comparando ciclo fixo e algoritmo pelas métricas de D3
  (script ou testes), com resultados para o relatório.
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
- [x] Contrato MQTT (`cmd`, `state`, `status`) e CLI `monitor`/`set`/`demo`
- [x] Broker Mosquitto no Pi e comunicação Pi ↔ ESP32 validada
- [x] Firmware dos 4 semáforos: resistor compartilhado, modos local/remote/test, rejeição de conflito A × B,
  timeout com volta ao ciclo local, firmware de teste de montagem
- [x] Documentação: arquitetura (README), AGENTS.md, tutorial de testes do ESP32
