#pragma once
#include <Arduino.h>

#define INTERSECTION_ID "cruzamento1"

// ---------------------------------------------------------------------------
// Hardware: ESP32 DevKit 38 pinos (ESP-WROOM-32).
// LEDs ativos em HIGH (pino -> LED -> resistor -> GND).
// Cada semáforo tem UM resistor compartilhado pelos 3 LEDs: nunca acender
// mais de um LED do mesmo semáforo ao mesmo tempo.
// Não usar 1 e 3 (Serial) nem 6 a 11 (flash). 0, 2 e 15 são pinos de boot;
// em algumas placas há um LED azul ligado ao GPIO 2 (a da maquete não tem).
// ---------------------------------------------------------------------------

static const uint8_t NUM_ROADS = 4;

// Pinos por semáforo: {vermelho, amarelo, verde}.
// S1..S4 correspondem às vias N, L, S, O do protocolo MQTT.
const int sem[NUM_ROADS][3] = {
    {15, 2, 0},    // S1 = N
    {4, 16, 17},   // S2 = L
    {5, 18, 19},   // S3 = S (ainda não montado)
    {21, 22, 23},  // S4 = O (ainda não montado)
};
static const char *const ROAD_NAMES[NUM_ROADS] = {"N", "L", "S", "O"};

// Via de cada semáforo: 0 = via A (S1 + S3), 1 = via B (S2 + S4).
// As vias A e B nunca podem estar em verde/amarelo ao mesmo tempo.
static const uint8_t ROAD_GROUP[NUM_ROADS] = {0, 1, 0, 1};

// Ciclo local (usado quando o Pi não está mandando comandos).
static const uint32_t TEMPO_VERDE_MS = 5000;
static const uint32_t TEMPO_AMARELO_MS = 2000;
static const uint32_t TEMPO_VERMELHO_GERAL_MS = 1000;

// Modo de teste: cada LED aceso por este tempo, um de cada vez.
static const uint32_t TEMPO_TESTE_LED_MS = 500;

// Sem comando do Pi por este tempo => volta ao ciclo local.
static const uint32_t COMMAND_TIMEOUT_MS = 10000;

// Pausa no fim de cada loop() para ceder CPU ao Wi-Fi/TCP (não é temporização).
static const uint32_t LOOP_YIELD_MS = 10;

// Intervalo entre tentativas de conexão ao broker.
static const uint32_t MQTT_RETRY_MS = 5000;
