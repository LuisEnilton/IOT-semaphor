#pragma once
#include <Arduino.h>

#define INTERSECTION_ID "cruzamento1"

// Pinos dos LEDs por via: {vermelho, amarelo, verde}. Ordem das vias: N, L, S, O.
static const uint8_t NUM_ROADS = 4;
static const char *ROAD_NAMES[NUM_ROADS] = {"N", "L", "S", "O"};
static const uint8_t LED_PINS[NUM_ROADS][3] = {
    {16, 17, 18},  // N
    {19, 21, 22},  // L
    {23, 25, 26},  // S
    {27, 32, 33},  // O
};

// Sem comando do Pi por este tempo => modo seguro (amarelo piscante).
static const uint32_t COMMAND_TIMEOUT_MS = 10000;
