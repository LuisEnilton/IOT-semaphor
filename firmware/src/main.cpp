// Semáforo (ESP32): recebe comandos via MQTT e acende os LEDs. Ver docs/mqtt-topics.md.
#include <Arduino.h>
#include <ArduinoJson.h>
#include <PubSubClient.h>
#include <WiFi.h>

#include "config.h"
#include "secrets.h"

enum LightState : uint8_t { RED, YELLOW, GREEN, OFF, FLASH_YELLOW };
static const char *STATE_NAMES[] = {"red", "yellow", "green", "off", "flash_yellow"};

static const char *T_CMD = "semaphor/" INTERSECTION_ID "/cmd";
static const char *T_STATE = "semaphor/" INTERSECTION_ID "/state";
static const char *T_STATUS = "semaphor/" INTERSECTION_ID "/status";

WiFiClient wifi;
PubSubClient mqtt(wifi);
LightState roads[NUM_ROADS];
uint32_t lastCmdMs = 0;
bool safeMode = true;

static void writeLeds(uint8_t road, bool r, bool y, bool g) {
  digitalWrite(LED_PINS[road][0], r);
  digitalWrite(LED_PINS[road][1], y);
  digitalWrite(LED_PINS[road][2], g);
}

static void render() {
  bool blink = (millis() / 500) % 2;
  for (uint8_t i = 0; i < NUM_ROADS; i++) {
    switch (roads[i]) {
      case RED: writeLeds(i, 1, 0, 0); break;
      case YELLOW: writeLeds(i, 0, 1, 0); break;
      case GREEN: writeLeds(i, 0, 0, 1); break;
      case FLASH_YELLOW: writeLeds(i, 0, blink, 0); break;
      default: writeLeds(i, 0, 0, 0);
    }
  }
}

static void publishState() {
  JsonDocument doc;
  doc["safe_mode"] = safeMode;
  for (uint8_t i = 0; i < NUM_ROADS; i++) doc["roads"][ROAD_NAMES[i]] = STATE_NAMES[roads[i]];
  char buf[256];
  size_t n = serializeJson(doc, buf);
  mqtt.publish(T_STATE, (const uint8_t *)buf, n, true);
}

static void enterSafeMode() {
  Serial.println("[safe] modo seguro: amarelo piscante");
  safeMode = true;
  for (auto &r : roads) r = FLASH_YELLOW;
  if (mqtt.connected()) publishState();
}

// Payload: {"roads": {"N": "green", "S": "green", "L": "red", "O": "red"}}
static void onMessage(char *topic, byte *payload, unsigned int len) {
  JsonDocument doc;
  if (deserializeJson(doc, payload, len)) return;
  JsonObject obj = doc["roads"];
  if (obj.isNull()) return;
  for (uint8_t i = 0; i < NUM_ROADS; i++) {
    const char *s = obj[ROAD_NAMES[i]];
    if (!s) continue;
    for (uint8_t k = 0; k < 5; k++)
      if (!strcmp(s, STATE_NAMES[k])) roads[i] = (LightState)k;
  }
  Serial.printf("[cmd] %.*s\n", (int)len, (const char *)payload);
  safeMode = false;
  lastCmdMs = millis();
  publishState();
}

static void connectWifi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.mode(WIFI_STA);
  Serial.printf("[wifi] conectando a %s...\n", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 10000) {
    render();  // mantém o amarelo piscante enquanto tenta
    delay(50);
  }
}

static void connectMqtt() {
  if (WiFi.status() != WL_CONNECTED || mqtt.connected()) return;
  String id = String("esp32-") + INTERSECTION_ID;
  // Last Will: o broker publica "offline" se o ESP32 cair.
  if (mqtt.connect(id.c_str(), nullptr, nullptr, T_STATUS, 1, true, "offline")) {
    Serial.println("[mqtt] conectado");
    mqtt.publish(T_STATUS, "online", true);
    mqtt.subscribe(T_CMD, 1);
    publishState();
  }
}

void setup() {
  Serial.begin(115200);
  Serial.println("\n[boot] semaforo " INTERSECTION_ID);
  for (auto &pins : LED_PINS)
    for (uint8_t p : pins) pinMode(p, OUTPUT);
  mqtt.setServer(MQTT_HOST, MQTT_PORT);
  mqtt.setCallback(onMessage);
  enterSafeMode();
}

void loop() {
  connectWifi();
  connectMqtt();
  mqtt.loop();
  if (!safeMode && millis() - lastCmdMs > COMMAND_TIMEOUT_MS) enterSafeMode();
  render();
  delay(10);
}
