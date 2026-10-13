// Prueba rudimentaria del enlace USB: SIN LCD. Solo usa el LED integrado (pin 13, "L").
//
//   Llega "D,bx,by,br,aid\n" con bola       -> LED encendido fijo
//   Llega "D,-1,-1,-1,-1\n" (sin bola)      -> LED apagado
//   Sin datos validos en 3 s (o al arrancar) -> LED parpadea lento (sin enlace)
//   Linea invalida                           -> responde "ERR"
// Cada linea valida se devuelve como "OK bx by br aid" (sirve para verificar ida y vuelta).
#include <Arduino.h>
#include <stdio.h>

static const unsigned long BAUD = 115200;
static const unsigned long TIMEOUT_MS = 3000;

static char buf[40];
static uint8_t n = 0;
static bool overflow = false;
static unsigned long lastOk = 0;
static bool haveData = false;
static bool ballOn = false;

static void handleLine(const char* s) {
  int bx, by, br, id;
  if (sscanf(s, "D,%d,%d,%d,%d", &bx, &by, &br, &id) != 4) {
    Serial.println(F("ERR"));
    return;
  }
  lastOk = millis();
  haveData = true;
  ballOn = (bx >= 0);
  Serial.print(F("OK "));
  Serial.print(bx);
  Serial.print(' ');
  Serial.print(by);
  Serial.print(' ');
  Serial.print(br);
  Serial.print(' ');
  Serial.println(id);
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  Serial.begin(BAUD);
  for (int i = 0; i < 3; i++) {  // 3 parpadeos rapidos = arranque (tras el auto-reset por DTR)
    digitalWrite(LED_BUILTIN, HIGH);
    delay(120);
    digitalWrite(LED_BUILTIN, LOW);
    delay(120);
  }
}

void loop() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      if (!overflow && n > 0) {
        buf[n] = 0;
        handleLine(buf);
      }
      n = 0;
      overflow = false;
    } else if (n < sizeof(buf) - 1) {
      buf[n++] = c;
    } else {
      overflow = true;  // linea demasiado larga: se descarta entera
    }
  }

  unsigned long now = millis();
  bool linkOk = haveData && (now - lastOk < TIMEOUT_MS);
  if (linkOk) {
    digitalWrite(LED_BUILTIN, ballOn ? HIGH : LOW);
  } else {
    digitalWrite(LED_BUILTIN, ((now / 500) % 2) ? HIGH : LOW);
  }
}
