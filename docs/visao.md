# Visão computacional: fila de veículos por via

O Pi conta quantos veículos esperam em cada via (`N`, `L`, `S`, `O`) com a câmera e o
[Ultralytics YOLO26](https://docs.ultralytics.com/guides/raspberry-pi/). O controlador de fases vai usar
essa contagem para decidir o tempo de verde.

```
câmera (picamera2) -> YOLO26n NCNN -> caixas -> ponto de apoio na ROI da via -> mediana -> {N: 3, L: 0, ...}
       vision.py                       vision.py            counting.py            counting.py
```

- `counting.py` é lógica pura e testada no CI. Contém `VehicleCounter`, `count_by_roi`, `Smoother` e
  `SimulatedCounter`.
- `vision.py` depende do hardware e do extra `vision`. Contém `Camera`, `YoloCounter` e `draw`.

## 1. Câmera

A câmera atual é uma OV5647 (Camera Module v1.3), ligada no conector CSI do Pi 5. Uma Camera Module 3
precisaria de um cabo adaptador de 15 para 22 pinos.

```
rpicam-hello --list-cameras     # deve listar a câmera
rpicam-hello -t 5000            # preview (precisa de tela)
```

Posicione a câmera **de cima**, enquadrando as 4 aproximações do cruzamento.

## 2. Instalação (no Pi)

```
make setup-pi        # se ainda não fez (venv com --system-site-packages, para enxergar o picamera2)
make setup-vision    # pip install -e "edge[dev,vision]" (ultralytics + torch CPU) e cria edge/rois.json
make vision-export   # baixa o yolo26n.pt e exporta para edge/yolo26n_ncnn_model/
```

Usamos o venv do projeto, e não o Docker do artigo da Raspberry Pi. Assim o picamera2 do apt continua
acessível.

Se aparecer `Illegal instruction` ou um torch com CUDA, reinstale o torch CPU:
`edge/.venv/bin/pip install --force-reinstall torch torchvision --index-url https://download.pytorch.org/whl/cpu`.

**Por que NCNN?** Benchmark da Ultralytics no Pi 5, YOLO26n com imgsz 640:

| Formato | Tempo por imagem |
|---|---|
| PyTorch | ~299 ms |
| ONNX | ~126 ms |
| **NCNN** | **~67 ms** |

Medido no nosso Pi 5 (nov/2026, com o desktop, VS Code e Chromium abertos): de 100 a 400 ms por leitura,
incluindo captura, pré e pós-processamento. Para medir fila isso basta. Sem a interface gráfica, fica
mais rápido.

Só os tamanhos `n` e `s` são viáveis no Pi. Para ganhar velocidade, use `VISION_IMGSZ=320`.

## 3. ROIs (uma região por via)

1. `make snapshot` (ou `semaphor-edge snapshot`) salva um frame em `edge/snapshots/`.
2. Abra a imagem num editor qualquer (GIMP, por exemplo) e anote os cantos da área de **espera** de cada
   via, em pixels. O frame padrão tem 640×480.
3. Edite `edge/rois.json`, que tem o mesmo formato de `rois.example.json`. Esse arquivo é local e
   ignorado pelo git.
4. `make count` abre a janela com as caixas detectadas, o ponto de apoio de cada veículo (o centro da
   base da caixa) e as ROIs com a contagem. Ajuste até a contagem bater. Pressione `q` para sair.

Uma detecção conta para a via cuja ROI contém o seu ponto de apoio. Detecções fora de todas as ROIs são
ignoradas. A contagem final é a mediana das últimas 5 leituras, para filtrar falhas de um só frame.

## 4. O que conta como veículo

Isso é configurado no `edge/.env`:

```
VISION_MODEL=yolo26n_ncnn_model
VISION_CLASSES=car,truck,bus     # nomes de classes COCO; vazio = todas
VISION_CONF=0.4
VISION_IMGSZ=640
```

O modelo pré-treinado (COCO) pode **não** reconhecer os carrinhos da maquete. Primeiro teste com
`make count`. Se não funcionar, há duas saídas:

- **Simular:** use objetos que o COCO detecta bem, por exemplo `VISION_CLASSES=bottle,cup`, e coloque
  garrafas ou copos na via.
- **Fine-tuning:**
  1. colete de 150 a 300 frames com `semaphor-edge snapshot`, variando posição, quantidade e luz;
  2. anote os frames no formato YOLO, com a classe `car` (Roboflow ou CVAT);
  3. treine **no notebook ou no Colab**, não no Pi:
     `yolo train model=yolo26n.pt data=maquete.yaml epochs=100 imgsz=640`;
  4. copie o `runs/detect/train/weights/best.pt` para `edge/` no Pi;
  5. exporte com `yolo export model=best.pt format=ncnn`;
  6. aponte `VISION_MODEL=best_ncnn_model` e `VISION_CLASSES=car`.

Pesos (`*.pt`, `*_ncnn_model/`), datasets e snapshots não vão para o git.

## 5. Sem câmera

`semaphor-edge count --sim` gera filas simuladas: cada via varia ±1 veículo por leitura. Isso permite
desenvolver o controlador no notebook. No código, qualquer classe com `counts() -> dict[str, int]` serve
como `VehicleCounter`.

## Integração com o controlador (próximo passo)

A inferência leva dezenas a centenas de ms. Ela **não pode** atrasar o reenvio de comandos a cada 2 s,
que impede o ESP32 de voltar ao ciclo local. Por isso, rode o `YoloCounter` numa thread separada e deixe o controlador ler
sempre a última contagem.
