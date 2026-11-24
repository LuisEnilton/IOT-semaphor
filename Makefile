.PHONY: setup setup-pi setup-vision vision-export broker lint test fw-build fw-upload fw-monitor monitor demo count snapshot
VENV := $(CURDIR)/edge/.venv

setup:        ## notebook: venv isolado + dependências
	python3 -m venv $(VENV) && $(VENV)/bin/pip install -U pip && $(VENV)/bin/pip install -e "edge[dev]"
	@test -f edge/.env || cp edge/.env.example edge/.env
	@test -f firmware/include/secrets.h || cp firmware/include/secrets.example.h firmware/include/secrets.h

setup-pi:     ## Raspberry Pi: venv com acesso aos pacotes do apt (picamera2/libcamera)
	sudo apt install -y mosquitto mosquitto-clients python3-picamera2
	python3 -m venv --system-site-packages $(VENV) && $(VENV)/bin/pip install -e "edge[dev]"
	@test -f edge/.env || cp edge/.env.example edge/.env
	printf 'listener 1883\nallow_anonymous true\n' | sudo tee /etc/mosquitto/conf.d/dev.conf
	sudo systemctl enable --now mosquitto && sudo systemctl restart mosquitto

setup-vision: ## Raspberry Pi: instala Ultralytics (YOLO26) no venv e copia o modelo de ROIs
	$(VENV)/bin/pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu  # sem CUDA
	$(VENV)/bin/pip install -e "edge[dev,vision]"
	@test -f edge/rois.json || cp edge/rois.example.json edge/rois.json
vision-export: ## baixa o YOLO26n e exporta para NCNN (formato mais rápido no CPU do Pi)
	cd edge && $(VENV)/bin/yolo export model=yolo26n.pt format=ncnn imgsz=640

broker:       ## broker local via Docker (notebook)
	docker compose up -d

lint:
	$(VENV)/bin/ruff check edge && $(VENV)/bin/ruff format --check edge
test:
	cd edge && $(VENV)/bin/pytest
fw-build:
	cd firmware && $(VENV)/bin/pio run
fw-upload:
	cd firmware && $(VENV)/bin/pio run -t upload
fw-monitor:
	cd firmware && $(VENV)/bin/pio device monitor
monitor:
	cd edge && $(VENV)/bin/semaphor-edge monitor
demo:
	cd edge && $(VENV)/bin/semaphor-edge demo
count:
	cd edge && $(VENV)/bin/semaphor-edge count --show
snapshot:
	cd edge && $(VENV)/bin/semaphor-edge snapshot
