#include <Arduino.h>
#include <Wire.h>
#include <hd44780.h>
#include <hd44780ioClass/hd44780_I2Cexp.h>

hd44780_I2Cexp lcd;

void setup() {
    Serial.begin(115200);
    int status = lcd.begin(16, 2);
    Serial.print("begin status: ");
    Serial.println(status);
    if (status) hd44780::fatalError(status);  // parpadea el LED L con el código
    lcd.print("Hola Braulio");
    lcd.setCursor(0, 1);
    lcd.print("hd44780 OK");
}

void loop() {}