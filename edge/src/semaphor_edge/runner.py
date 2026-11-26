"""Roda o controlador de fases no Pi e conversa com o ESP32 via MQTT.

- Runner: decide o que publicar (troca de fase + heartbeat). Lógica pura, testável.
- StateMonitor: compara `state`/`status` do ESP32 com o que foi enviado e gera avisos.
- run(): liga tudo ao broker (paho-mqtt) e roda até Ctrl+C.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable

import paho.mqtt.client as mqtt

from .config import Config
from .phases import GreenPolicy, PhaseController, Timing, start_phase_for
from .protocol import build_cmd, topic

log = logging.getLogger("semaphor_edge")

# Firmware volta ao ciclo local após 10 s sem comando (COMMAND_TIMEOUT_MS).
ESP32_TIMEOUT_S = 10.0


class Runner:
    """Publica o comando a cada troca de fase e a cada `heartbeat_s` (heartbeat).

    Antes de começar, espera até `wait_state_s` pelo `state` retido do ESP32 para
    assumir o controle sem cortar um verde (ver phases.start_phase_for).
    """

    def __init__(
        self,
        publish: Callable[[str], None],
        now: float,
        timing: Timing | None = None,
        heartbeat_s: float = 1.0,
        green_policy: GreenPolicy | None = None,
        wait_state_s: float = 2.0,
    ) -> None:
        if not 0 < heartbeat_s < ESP32_TIMEOUT_S / 2:
            raise ValueError(f"heartbeat deve estar entre 0 e {ESP32_TIMEOUT_S / 2} s")
        self._publish = publish
        self._timing = timing
        self._green_policy = green_policy
        self.heartbeat_s = heartbeat_s
        self._created = now
        self._wait_state_s = wait_state_s
        self._initial_roads: dict[str, str] | None = None
        self._state_seen = False
        self._last_sent_at: float | None = None
        self._resync_roads: dict[str, str] | None = None
        self.controller: PhaseController | None = None
        # Últimos estados enviados (atual e anterior, que pode estar em trânsito).
        self.recent_roads: list[dict[str, str]] = []

    def observe_state(self, mode: str | None, roads: dict[str, str] | None) -> None:
        """Recebe cada `state` do ESP32 (chamado pela thread do MQTT).

        - Antes de assumir: guarda o estado para começar sem cortar um verde.
        - Depois: se o ESP32 aparece fora do modo `remote` (reiniciou, reconectou ou ficou
          sem comandos), pede uma ressincronização, porque o ciclo local dele pode estar
          numa fase diferente da do Pi.
        """
        if self.controller is None:
            if not self._state_seen:
                self._state_seen = True
                self._initial_roads = roads
        elif mode != "remote":
            self._resync_roads = roads or {}

    def step(self, now: float) -> None:
        if self.controller is None:
            if not self._state_seen and now - self._created < self._wait_state_s:
                return
            start = start_phase_for(self._initial_roads)
            self.controller = PhaseController(now, self._timing, self._green_policy, start)
            self._log_phase()
            changed = True
        elif self._resync_roads is not None:
            roads, self._resync_roads = self._resync_roads, None
            start = start_phase_for(roads)
            log.warning("ESP32 fora do modo remote; retomando a partir de %s", start.name)
            self.controller = PhaseController(now, self._timing, self._green_policy, start)
            self._log_phase()
            changed = True
        else:
            changed = self.controller.update(now)
            if changed:
                self._log_phase()

        if changed or self._last_sent_at is None or now - self._last_sent_at >= self.heartbeat_s:
            roads = self.controller.roads
            self._publish(build_cmd(roads))
            self._last_sent_at = now
            if not self.recent_roads or self.recent_roads[-1] != roads:
                self.recent_roads = [*self.recent_roads, roads][-2:]

    def _log_phase(self) -> None:
        c = self.controller
        log.info("fase %-11s %4.1f s  %s", c.phase.name, c.phase_duration, c.roads)


class StateMonitor:
    """Gera avisos só quando a situação muda (sem repetir a cada mensagem).

    Os métodos retornam (ok, mensagem) ou None se nada mudou.
    """

    def __init__(self) -> None:
        self.online: bool | None = None
        self._last_issue: str | None = "inicio"

    def on_status(self, payload: str) -> tuple[bool, str] | None:
        online = payload == "online"
        if online == self.online:
            return None
        self.online = online
        if online:
            return True, "ESP32 online"
        return False, "ESP32 OFFLINE: perdeu a conexão com o broker"

    def on_state(self, payload: str, sent: list[dict[str, str]]) -> tuple[bool, str] | None:
        if not sent:
            return None  # o Pi ainda não assumiu; o ESP32 em modo local é o esperado
        try:
            data = json.loads(payload)
            mode, roads = data["mode"], data["roads"]
        except (ValueError, KeyError, TypeError):
            issue = "state inválido recebido do ESP32"
        else:
            if mode != "remote":
                issue = f"ESP32 em modo {mode}: não está seguindo o Pi"
            elif roads not in sent:
                issue = "state do ESP32 diverge do comando enviado (comando rejeitado?)"
            else:
                issue = None
        if issue == self._last_issue:
            return None
        self._last_issue = issue
        if issue is None:
            return True, "ESP32 seguindo os comandos do Pi"
        return False, issue


def _parse_state(payload: str) -> tuple[str | None, dict[str, str] | None]:
    try:
        data = json.loads(payload)
        mode, roads = data.get("mode"), data.get("roads")
    except (ValueError, AttributeError):
        return None, None
    return mode, roads if isinstance(roads, dict) else None


def run(
    cfg: Config,
    timing: Timing,
    heartbeat_s: float = 1.0,
    green_policy: GreenPolicy | None = None,
    tick_s: float = 0.05,
    on_tick: Callable[[float, dict[str, str]], None] | None = None,
) -> None:
    """Roda até Ctrl+C. `on_tick(now, roads)` é chamado a cada volta com o estado atual
    das vias (usado para avançar o tráfego simulado)."""
    cmd_topic = topic(cfg.intersection_id, "cmd")
    state_topic = topic(cfg.intersection_id, "state")
    status_topic = topic(cfg.intersection_id, "status")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"pi-{cfg.intersection_id}")
    client.reconnect_delay_set(min_delay=1, max_delay=10)
    monitor = StateMonitor()
    stopping = False

    def publish(payload: str) -> None:
        # Sem conexão, descarta: comandos velhos não devem ser entregues depois.
        if client.is_connected():
            client.publish(cmd_topic, payload, qos=1)

    runner = Runner(publish, time.monotonic(), timing, heartbeat_s, green_policy)

    def on_connect(c, _userdata, _flags, reason_code, _props) -> None:
        if reason_code.is_failure:
            log.warning("broker recusou a conexão: %s", reason_code)
            return
        log.info("conectado ao broker %s:%d", cfg.mqtt_host, cfg.mqtt_port)
        c.subscribe([(state_topic, 0), (status_topic, 1)])

    def on_disconnect(_c, _userdata, _flags, reason_code, _props) -> None:
        if not stopping:
            log.warning("desconectado do broker (%s); tentando reconectar", reason_code)

    def on_message(_c, _userdata, msg) -> None:
        payload = msg.payload.decode(errors="replace")
        if msg.topic == status_topic:
            note = monitor.on_status(payload)
        else:
            runner.observe_state(*_parse_state(payload))
            note = monitor.on_state(payload, runner.recent_roads)
        if note:
            ok, text = note
            log.log(logging.INFO if ok else logging.WARNING, text)

    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    log.info(
        "controlador: verde %.1f s, amarelo %.1f s, vermelho geral %.1f s, heartbeat %.1f s",
        timing.green_s,
        timing.yellow_s,
        timing.all_red_s,
        heartbeat_s,
    )
    client.connect_async(cfg.mqtt_host, cfg.mqtt_port)
    client.loop_start()
    try:
        while True:
            now = time.monotonic()
            if on_tick and runner.controller:
                on_tick(now, runner.controller.roads)
            runner.step(now)
            time.sleep(tick_s)
    except KeyboardInterrupt:
        log.info("encerrando; o ESP32 volta ao ciclo local em ~%.0f s", ESP32_TIMEOUT_S)
    finally:
        stopping = True
        client.disconnect()
        client.loop_stop()
