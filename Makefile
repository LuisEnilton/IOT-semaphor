.PHONY: setup setup-pi broker lint test fw-build fw-upload fw-monitor monitor demo
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
fw-monitor:
	cd firmware && $(VENV)/bin/pio device monitor
monitor:
	cd edge && $(VENV)/bin/semaphor-edge monitor
demo:
	cd edge && $(VENV)/bin/semaphor-edge demo
