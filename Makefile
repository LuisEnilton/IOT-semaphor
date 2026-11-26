.PHONY: setup setup-pi broker lint test fw-build fw-upload fw-test fw-monitor monitor run run-sim simular demo
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
fw-test:      ## grava o firmware de teste de montagem (LEDs em sequência, em repetição)
	cd firmware && $(VENV)/bin/pio run -e teste -t upload
fw-monitor:
	cd firmware && $(VENV)/bin/pio device monitor
monitor:
	cd edge && $(VENV)/bin/semaphor-edge monitor
run:          ## controlador de fases (Pi comanda o ESP32); Ctrl+C para parar
	cd edge && $(VENV)/bin/semaphor-edge run
run-sim:      ## controlador com tráfego simulado e algoritmo de fila (verde dinâmico)
	cd edge && $(VENV)/bin/semaphor-edge run --simulado
simular:      ## compara ciclo fixo x algoritmo de fila (offline, ~1 min)
	cd edge && $(VENV)/bin/semaphor-edge simular
demo: run     ## nome antigo do run
