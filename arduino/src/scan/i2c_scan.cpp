// Escáner I2C: imprime por serie la dirección de cada dispositivo que responde.
// Sirve para saber si el LCD está conectado y con qué dirección (0x27, 0x3F, ...).
// Se compila solo con el entorno "scan" (ver platformio.ini).
#include <Arduino.h>
#include <Wire.h>

void setup() {
  Serial.begin(115200);
  Wire.begin();
  delay(1500);
}

void loop() {
  uint8_t found = 0;
  Serial.println(F("Buscando dispositivos I2C..."));
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.print(F("  encontrado en 0x"));
      if (addr < 16) Serial.print('0');
      Serial.println(addr, HEX);
      found++;
    }
  }
  if (found == 0) Serial.println(F("  ninguno: revisa SDA/SCL (A4/A5), GND y 5V"));
  Serial.println();
  delay(3000);
}
