// main.cpp (proyecto PlatformIO) — recibe por USB-serie líneas de texto y las muestra en un LCD 16x2 I2C.
//
// Protocolo v2 (ASCII, una línea por mensaje, 115200 baud, fin de línea '\n'):
//     M,<bola>,<n>,<id1>,...,<idn>
//   bola : 1 si se ve la pelota, 0 si no (solo como indicador de depuración)
//   n    : cuántos ArUco se reportan (0..8); permite detectar líneas truncadas
//   idk  : ids de los ArUco, el más grande (el más cercano) primero
// Ejemplos:  M,1,3,7,12,3     M,0,0     M,1,1,5
//
// Sentido contrario (Arduino -> celular): al terminar setup() se envía  B\n  ("arranqué"). El botón de
// reinicio solo reinicia el ATmega; el CH340 sigue alimentado y el USB no se corta, así que el celular
// solo puede enterarse por este mensaje (link.py lo usa para reiniciar la visión).
//
// Compatibilidad: sigue aceptando el formato anterior  D,<bx>,<by>,<br>,<aid>
// (bola = bx>=0; un solo ArUco si aid>=0), para poder teclear pruebas viejas.
//
// Pantalla (16x2):
//   fila 1:  ArUco x3 Bola:si
//   fila 2:  7 12 3          (si no caben todos, termina en '+';  '-' si no hay)
//
// Cableado (Uno/Nano): LCD GND->GND, VCC->5V, SDA->A4, SCL->A5.
//   (Mega: SDA 20, SCL 21. Leonardo: SDA 2, SCL 3.)
// Librería: LiquidCrystal_I2C, declarada en platformio.ini (lib_deps); PlatformIO la descarga sola.
// Si no se ve texto: ajusta el potenciómetro de contraste del módulo, o prueba 0x3F.
//
// Diseño: lo que llega por USB se trata como NO confiable. Se arma la línea
// carácter a carácter con un tope de longitud, se descarta lo que no parsea, y si
// pasa TIMEOUT_MS sin un mensaje válido se avisa "Sin enlace" (un valor viejo en
// pantalla parecería un dato actual).

#include <Arduino.h>      // en un .ino esto se añade solo; en .cpp hay que ponerlo
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <stdlib.h>

const uint8_t  LCD_ADDR   = 0x27;
const uint32_t BAUD       = 115200;
const uint32_t TIMEOUT_MS = 10000;   // la cámara entrega una foto cada pocos segundos
const uint8_t  MAX_IDS    = 8;       // ocho ids de 3 cifras: ~40 caracteres de línea

LiquidCrystal_I2C lcd(LCD_ADDR, 16, 2);

char     line[64];
uint8_t  len = 0;
bool     discarding = false;    // línea demasiado larga: ignorar hasta el siguiente '\n'
uint32_t lastRx = 0;
bool     timedOut = false;

struct Msg {
  bool    ball;
  uint8_t n;
  int     ids[MAX_IDS];
};

// Escribe una fila completa (rellena con espacios: no hace falta lcd.clear(), que parpadea).
void printRow(uint8_t row, const char* text) {
  char out[17];
  snprintf(out, sizeof(out), "%-16s", text);
  lcd.setCursor(0, row);
  lcd.print(out);
}

// --- análisis de la línea (sin sscanf: la lista de ids es de longitud variable) ---
bool eat(const char*& p, char c) {
  if (*p != c) return false;
  ++p;
  return true;
}

bool readInt(const char*& p, int& v) {
  char* end;
  long x = strtol(p, &end, 10);
  if (end == p) return false;
  v = (int)x;
  p = end;
  return true;
}

// M,<bola>,<n>,<id>...   Rechaza todo lo que no cuadre exactamente.
bool parseM(const char* s, Msg& m) {
  const char* p = s;
  int ball, n;
  if (!eat(p, 'M') || !eat(p, ',') || !readInt(p, ball) || (ball != 0 && ball != 1)) return false;
  if (!eat(p, ',') || !readInt(p, n) || n < 0 || n > MAX_IDS) return false;
  for (int i = 0; i < n; i++) {
    int id;
    if (!eat(p, ',') || !readInt(p, id) || id < 0 || id > 999) return false;
    m.ids[i] = id;
  }
  if (*p != '\0') return false;       // sobra algo: línea corrupta
  m.ball = (ball == 1);
  m.n = (uint8_t)n;
  return true;
}

// D,<bx>,<by>,<br>,<aid>  (formato v1)
bool parseD(const char* s, Msg& m) {
  int bx, by, br, aid;
  if (sscanf(s, "D,%d,%d,%d,%d", &bx, &by, &br, &aid) != 4) return false;
  m.ball = (bx >= 0);
  m.n = (aid >= 0) ? 1 : 0;
  if (m.n) m.ids[0] = aid;
  return true;
}

bool parseLine(const char* s, Msg& m) {
  if (s[0] == 'M') return parseM(s, m);
  if (s[0] == 'D') return parseD(s, m);
  return false;
}

// Fila 2: ids separados por espacio. Si no caben todos (16 columnas), los que quepan y '+'.
void formatIds(const Msg& m, char* out /* 17 */) {
  if (m.n == 0) { snprintf(out, 17, "-"); return; }
  char tmp[8];
  uint8_t total = 0;
  for (uint8_t i = 0; i < m.n; i++) {
    total += snprintf(tmp, sizeof(tmp), "%d", m.ids[i]) + (i ? 1 : 0);
  }
  uint8_t limit = (total <= 16) ? 16 : 15;     // si hay que cortar, se reserva sitio para '+'
  uint8_t pos = 0, shown = 0;
  for (uint8_t i = 0; i < m.n; i++) {
    uint8_t need = snprintf(tmp, sizeof(tmp), "%d", m.ids[i]) + (i ? 1 : 0);
    if (pos + need > limit) break;
    if (i) out[pos++] = ' ';
    for (const char* t = tmp; *t; ++t) out[pos++] = *t;
    shown++;
  }
  if (shown < m.n) out[pos++] = '+';
  out[pos] = '\0';
}

void showData(const Msg& m) {
  char a[17], b[17];
  snprintf(a, sizeof(a), "ArUco x%d Bola:%s", m.n, m.ball ? "si" : "no");
  formatIds(m, b);
  printRow(0, a);
  printRow(1, b);
}

void handleLine(const char* s) {
  Msg m;
  if (!parseLine(s, m)) return;       // basura: se ignora
  lastRx = millis();
  timedOut = false;
  showData(m);
}

void setup() {
  Serial.begin(BAUD);
  lcd.init();
  lcd.backlight();
  printRow(0, "Enlace USB");
  printRow(1, "esperando datos");
  lastRx = millis();
  Serial.println(F("B"));       // anuncia el arranque (ver arriba); el celular reinicia la visión
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      if (!discarding && len > 0) {
        line[len] = '\0';
        handleLine(line);
      }
      len = 0;
      discarding = false;
      continue;
    }
    if (discarding) continue;
    if (len < sizeof(line) - 1) line[len++] = c;
    else { discarding = true; len = 0; }
  }

  if (!timedOut && (uint32_t)(millis() - lastRx) > TIMEOUT_MS) {
    timedOut = true;
    printRow(0, "Sin enlace");
    printRow(1, "sin datos nuevos");
  }
}
