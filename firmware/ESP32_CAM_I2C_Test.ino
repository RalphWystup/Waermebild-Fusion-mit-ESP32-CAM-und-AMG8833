/*
 * ESP32_CAM_I2C_Test.ino  (Version 2: probiert mehrere Pin-Paare)
 * Sucht den AMG8833 auf allen brauchbaren freien Pin-Kombinationen des
 * AI-Thinker ESP32-CAM. Der Sensor bleibt einfach angeschlossen; das
 * Programm testet reihum alle SDA/SCL-Zuordnungen aus den Pins
 * 13, 14, 15 und 2 und meldet, wo er antwortet.
 *
 * Damit findet sich auch der Fall "einer der Pins ist defekt" oder
 * "SDA/SCL doch vertauscht" automatisch. Sobald eine Kombination
 * GERAET meldet, ist das die Belegung fuer den Fusion-Sketch.
 *
 * Hinweis zu den Pins: IO16/IO0/IO1/IO3 sind tabu (PSRAM, Kameratakt,
 * UART). IO12 wird bewusst NICHT getestet: Die Pull-up-Widerstaende des
 * Sensormoduls wuerden dort die Boot-Spannungswahl verstellen. IO4 hat
 * die Blitz-LED. Bei IO2 gilt: mit angestecktem Sensor auf IO2 kann das
 * FLASHEN klemmen -- zum Flashen dann kurz abziehen.
 *
 * Board "AI Thinker ESP32-CAM", serieller Monitor 115200 Baud.
 */

#include <Wire.h>

// Kandidaten: {SDA, SCL}
const int PAARE[][2] = {
  {13, 14},   // Soll-Belegung
  {14, 13},   // vertauscht
  {15, 14},   // Ersatz fuer 13
  {14, 15},
  {13, 15},   // Ersatz fuer 14
  {15, 13},
  {2, 14},    // Ersatz mit IO2
  {14, 2},
  {2, 15},
  {15, 2},
  {13, 2},
  {2, 13},
};
const int ANZAHL = sizeof(PAARE) / sizeof(PAARE[0]);

void setup() {
  Serial.begin(115200);
  pinMode(4, OUTPUT);          // Blitz-LED (GPIO4) fest AUS -- sonst glimmt
  digitalWrite(4, LOW);        // sie und belastet die 3,3-V-Schiene
  delay(500);
  Serial.println("\n[START] I2C-Suchlauf ueber mehrere Pin-Paare ...");
  Serial.println("Sensor angeschlossen lassen; ein Durchlauf dauert ca. 25 s.\n");
}

void loop() {
  bool irgendwo = false;
  for (int p = 0; p < ANZAHL; p++) {
    int sda = PAARE[p][0], scl = PAARE[p][1];
    Serial.printf("SDA=%-2d SCL=%-2d : ", sda, scl);

    // Leitungszustand mit schwachen Pull-ups pruefen
    pinMode(sda, INPUT_PULLUP);
    pinMode(scl, INPUT_PULLUP);
    delay(5);
    if (!digitalRead(sda) || !digitalRead(scl)) {
      Serial.printf("%s%sklemmt auf LOW\n",
                    digitalRead(sda) ? "" : "SDA ",
                    digitalRead(scl) ? "" : "SCL ");
      continue;
    }

    // Bus scannen
    Wire.begin(sda, scl, 100000);
    int gefunden = 0;
    for (uint8_t adr = 0x08; adr < 0x78; adr++) {
      Wire.beginTransmission(adr);
      if (Wire.endTransmission() == 0) {
        Serial.printf("GERAET auf 0x%02X%s  ", adr,
                      (adr == 0x69 || adr == 0x68) ? " (= AMG8833!)" : "");
        gefunden++;
        irgendwo = true;
      }
    }
    if (!gefunden) Serial.print("nichts");
    Serial.println();
    Wire.end();
    delay(100);
  }
  Serial.println(irgendwo
    ? ">>> Treffer oben ablesen -- diese SDA/SCL-Belegung in den "
      "Fusion-Sketch eintragen. <<<\n"
    : ">>> Nirgends eine Antwort: Sensor nochmal am Display-Board "
      "gegenpruefen; sonst Kontakt der CAM-Stiftleiste verdaechtigen "
      "(nachloeten). Neuer Durchlauf ...\n");
  delay(3000);
}
