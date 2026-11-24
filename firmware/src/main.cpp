// Semáforo (ESP32): 4 semáforos, controlados pelo Pi via MQTT ou por um ciclo local.
// Ver docs/mqtt-topics.md e firmware/include/config.h.
//
// Modos:
//   local  - ciclo fixo A verde -> A amarelo -> vermelho geral -> B verde -> ... (sem Pi)
//   remote - estados definidos pelos comandos MQTT do Pi
//   test   - acende cada um dos 12 LEDs em sequência (envie 't' pela serial)
#include <Arduino.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include <WiFi.h>

#include "config.h"
#include "secrets.h"

enum LightState : uint8_t { RED, YELLOW, GREEN, OFF, FLASH_YELLOW, NUM_STATES };
static const char *const STATE_NAMES[NUM_STATES] = {"red", "yellow", "green", "off", "flash_yellow"};

enum Mode : uint8_t { MODE_LOCAL, MODE_REMOTE, MODE_TEST };
static const char *const MODE_NAMES[] = {"local", "remote", "test"};

static const char *T_CMD = "semaphor/" INTERSECTION_ID "/cmd";
static const char *T_STATE = "semaphor/" INTERSECTION_ID "/state";
static const char *T_STATUS = "semaphor/" INTERSECTION_ID "/status";

WiFiClient wifi;
PubSubClient mqtt(wifi);

LightState roads[NUM_ROADS];
Mode mode = MODE_LOCAL;
uint32_t lastCmdMs = 0;
uint32_t lastMqttTryMs = 0;
bool wifiUp = false;

// ---------------------------------------------------------------------------
// Ciclo local
// ---------------------------------------------------------------------------
struct Phase {
  LightState a, b;  // estado da via A e da via B
  uint32_t ms;
};
static const Phase CYCLE[] = {
    {GREEN, RED, TEMPO_VERDE_MS},     {YELLOW, RED, TEMPO_AMARELO_MS},
    {RED, RED, TEMPO_VERMELHO_GERAL_MS}, {RED, GREEN, TEMPO_VERDE_MS},
    {RED, YELLOW, TEMPO_AMARELO_MS},  {RED, RED, TEMPO_VERMELHO_GERAL_MS},
};
static const int8_t CYCLE_LEN = sizeof(CYCLE) / sizeof(CYCLE[0]);
static const int8_t PHASE_TRANSITION = -1;  // verdes viram amarelo antes do vermelho geral
int8_t phase = 0;
uint32_t phaseStartMs = 0;

// Modo de teste
uint8_t testIndex = 0;
uint32_t testStartMs = 0;

// ---------------------------------------------------------------------------
// LEDs
// ---------------------------------------------------------------------------
static void allLedsOff() {
  for (uint8_t r = 0; r < NUM_ROADS; r++)
    for (uint8_t c = 0; c < 3; c++) digitalWrite(sem[r][c], LOW);
}

// Acende no máximo um LED do semáforo (color = 0, 1, 2 ou -1 para nenhum).
// Resistor compartilhado: apaga os outros dois ANTES de acender o novo.
static void showColor(uint8_t road, int8_t color) {
  for (int8_t c = 0; c < 3; c++)
    if (c != color) digitalWrite(sem[road][c], LOW);
  if (color >= 0) digitalWrite(sem[road][color], HIGH);
}

static void render() {
  if (mode == MODE_TEST) return;  // o teste controla os LEDs diretamente
  bool blinkOn = (millis() / 500) % 2;
  for (uint8_t r = 0; r < NUM_ROADS; r++) {
    switch (roads[r]) {
      case RED: showColor(r, 0); break;
      case YELLOW: showColor(r, 1); break;
      case GREEN: showColor(r, 2); break;
      case FLASH_YELLOW: showColor(r, blinkOn ? 1 : -1); break;
      default: showColor(r, -1);
    }
  }
}

// ---------------------------------------------------------------------------
// Estado / MQTT
// ---------------------------------------------------------------------------
static bool isActive(LightState s) { return s == GREEN || s == YELLOW; }

// Conflito: alguma via A e alguma via B em verde/amarelo ao mesmo tempo.
static bool hasConflict(const LightState *s) {
  bool activeA = false, activeB = false;
  for (uint8_t r = 0; r < NUM_ROADS; r++)
    if (isActive(s[r])) (ROAD_GROUP[r] == 0 ? activeA : activeB) = true;
  return activeA && activeB;
}

static void publishState() {
  if (!mqtt.connected()) return;
  JsonDocument doc;
  doc["mode"] = MODE_NAMES[mode];
  for (uint8_t r = 0; r < NUM_ROADS; r++) doc["roads"][ROAD_NAMES[r]] = STATE_NAMES[roads[r]];
  char buf[256];
  size_t n = serializeJson(doc, buf);
  mqtt.publish(T_STATE, (const uint8_t *)buf, n, true);
}

static void applyPhase(int8_t p) {
  phase = p;
  phaseStartMs = millis();
  if (p == PHASE_TRANSITION) {
    for (auto &s : roads) s = isActive(s) ? YELLOW : RED;
  } else {
    for (uint8_t r = 0; r < NUM_ROADS; r++)
      roads[r] = ROAD_GROUP[r] == 0 ? CYCLE[p].a : CYCLE[p].b;
  }
  publishState();
}

static void startLocal() {
  Serial.println("[modo] local: ciclo fixo");
  mode = MODE_LOCAL;
  bool anyActive = false;
  for (auto s : roads) anyActive |= isActive(s);
  // Se havia verde/amarelo, passa pelo amarelo antes do vermelho geral.
  applyPhase(anyActive ? PHASE_TRANSITION : CYCLE_LEN - 1);
}

static void updateLocal() {
  uint32_t duration = phase == PHASE_TRANSITION ? TEMPO_AMARELO_MS : CYCLE[phase].ms;
  if (millis() - phaseStartMs < duration) return;
  applyPhase(phase == PHASE_TRANSITION ? CYCLE_LEN - 1 : (phase + 1) % CYCLE_LEN);
}

// Acende só o LED testIndex (um por vez no total) e informa na serial.
static void lightTestLed() {
  uint8_t r = testIndex / 3, c = testIndex % 3;
  testStartMs = millis();
  digitalWrite(sem[r][c], HIGH);
  Serial.printf("[teste] %2u/12 %s %-8s (GPIO %d)\n", testIndex + 1, SEM_NAMES[r], COLOR_NAMES[c],
                sem[r][c]);
}

static void startTest() {
  Serial.println("[modo] teste: 12 LEDs em sequencia");
  mode = MODE_TEST;
  allLedsOff();
  testIndex = 0;
  lightTestLed();
  publishState();
}

static void updateTest() {
  if (millis() - testStartMs < TEMPO_TESTE_LED_MS) return;
  digitalWrite(sem[testIndex / 3][testIndex % 3], LOW);
  if (++testIndex >= NUM_ROADS * 3) {
#ifdef MODO_TESTE
    testIndex = 0;  // build de teste: repete para sempre
#else
    for (auto &s : roads) s = RED;
    startLocal();
    return;
#endif
  }
  lightTestLed();
}

// Payload: {"roads": {"N": "green", "S": "green", "L": "red", "O": "red"}}
// Vias omitidas mantêm o estado atual. Comandos inválidos ou com conflito são ignorados.
static void onMessage(char *topic, byte *payload, unsigned int len) {
  Serial.printf("[cmd] %.*s\n", (int)len, (const char *)payload);
  if (mode == MODE_TEST) {
    Serial.println("[cmd] ignorado: modo de teste em andamento");
    return;
  }
  JsonDocument doc;
  if (deserializeJson(doc, payload, len)) {
    Serial.println("[cmd] rejeitado: JSON invalido");
    return;
  }
  JsonObject obj = doc["roads"];
  if (obj.isNull()) {
    Serial.println("[cmd] rejeitado: falta o campo roads");
    return;
  }
  LightState next[NUM_ROADS];
  memcpy(next, roads, sizeof(roads));
  for (uint8_t r = 0; r < NUM_ROADS; r++) {
    const char *s = obj[ROAD_NAMES[r]];
    if (!s) continue;
    uint8_t k = 0;
    while (k < NUM_STATES && strcmp(s, STATE_NAMES[k])) k++;
    if (k == NUM_STATES) {
      Serial.printf("[cmd] rejeitado: estado invalido '%s'\n", s);
      return;
    }
    next[r] = (LightState)k;
  }
  if (hasConflict(next)) {
    Serial.println("[cmd] rejeitado: vias A e B ativas ao mesmo tempo");
    return;
  }
  memcpy(roads, next, sizeof(roads));
  if (mode != MODE_REMOTE) Serial.println("[modo] remote: comandado pelo Pi");
  mode = MODE_REMOTE;
  lastCmdMs = millis();
  publishState();
}

static void updateNetwork() {
  bool up = WiFi.status() == WL_CONNECTED;
  if (up != wifiUp) {
    wifiUp = up;
    if (up) Serial.printf("[wifi] conectado, IP %s\n", WiFi.localIP().toString().c_str());
    else Serial.println("[wifi] desconectado, tentando reconectar");
  }
  if (!up || mqtt.connected()) return;
  if (millis() - lastMqttTryMs < MQTT_RETRY_MS) return;
  lastMqttTryMs = millis();
  String id = String("esp32-") + INTERSECTION_ID;
  // Last Will: o broker publica "offline" se o ESP32 cair.
  if (mqtt.connect(id.c_str(), nullptr, nullptr, T_STATUS, 1, true, "offline")) {
    Serial.println("[mqtt] conectado");
    mqtt.publish(T_STATUS, "online", true);
    mqtt.subscribe(T_CMD, 1);
    publishState();
  } else {
    Serial.printf("[mqtt] falhou (rc=%d), nova tentativa em %lus\n", mqtt.state(),
                  MQTT_RETRY_MS / 1000);
  }
}

// ---------------------------------------------------------------------------
void setup() {
  // Primeiro de tudo: todos os pinos como saída e em LOW.
  for (uint8_t r = 0; r < NUM_ROADS; r++)
    for (uint8_t c = 0; c < 3; c++) {
      pinMode(sem[r][c], OUTPUT);
      digitalWrite(sem[r][c], LOW);
    }
  for (auto &s : roads) s = RED;

  Serial.begin(115200);
#ifdef MODO_TESTE
  Serial.println("\n[boot] semaforo " INTERSECTION_ID);
#else
  Serial.println("\n[boot] semaforo " INTERSECTION_ID " (envie 't' para o modo de teste)");
#endif

  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);  // não bloqueia; o status é verificado no loop()
  Serial.printf("[wifi] conectando a %s...\n", WIFI_SSID);
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMessage);

#ifdef MODO_TESTE
  Serial.println("[boot] build MODO_TESTE: sequencia de LEDs em repeticao");
  startTest();
#else
  startLocal();
#endif
}

void loop() {
  if (Serial.available() && Serial.read() == 't' && mode != MODE_TEST) startTest();

  updateNetwork();
  mqtt.loop();

  switch (mode) {
    case MODE_LOCAL: updateLocal(); break;
    case MODE_TEST: updateTest(); break;
    case MODE_REMOTE:
      if (millis() - lastCmdMs > COMMAND_TIMEOUT_MS) startLocal();
      break;
  }
  render();
  // Pausa curta para ceder CPU às tarefas de Wi-Fi/TCP. Não é usada para temporização
  // (os tempos do semáforo vêm de millis()); sem ela o Wi-Fi e o MQTT ficam instáveis.
  delay(LOOP_YIELD_MS);
}
