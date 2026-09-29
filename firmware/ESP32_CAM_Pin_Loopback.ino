/*
 * ESP32_CAM_Pin_Loopback.ino
 * Brueckentest fuer die freien Pins des AI-Thinker ESP32-CAM.
 * Eine Drahtbruecke zwischen ZWEI Pins stecken (z. B. IO13 <-> IO14);
 * das Programm prueft laufend alle Paarungen aus 13, 14, 15 und 2 in
 * beide Richtungen (A treibt, B liest -- und umgekehrt).
 *
 * Anzeige alle 2 s, die gebrueckte Paarung muss "VERBINDUNG" melden:
 *   13<->14: VERBINDUNG   <- beide Pins samt Loetstellen in Ordnung
 *   13<->15: -
 *   ...
 * Meldet die gebrueckte Paarung dauerhaft "-", ist einer der beiden
 * Pins (oder seine Loetstelle an der Stiftleiste) defekt. Durch
 * Umstecken der Bruecke auf andere Paarungen laesst sich eingrenzen,
 * WELCHER Pin es ist (der Pin, der in keiner Paarung funktioniert).
 *
 * Board "AI Thinker ESP32-CAM", serieller Monitor 115200 Baud.
 * Sensor fuer diesen Test NICHT anschliessen.
 */

const int PINS[] = {13, 14, 15, 2};
const int N = sizeof(PINS) / sizeof(PINS[0]);

bool richtung_ok(int treiber, int leser) {
  // Leser passiv mit definiertem Gegen-Pegel, Treiber aktiv dagegen:
  pinMode(treiber, OUTPUT);

  pinMode(leser, INPUT_PULLDOWN);      // Leser wird nach unten gezogen ...
  digitalWrite(treiber, HIGH);         // ... Treiber muss ihn hochziehen
  delayMicroseconds(50);
  bool hoch_ok = digitalRead(leser);

  pinMode(leser, INPUT_PULLUP);        // Leser wird nach oben gezogen ...
  digitalWrite(treiber, LOW);          // ... Treiber muss ihn runterziehen
  delayMicroseconds(50);
  bool tief_ok = !digitalRead(leser);

  pinMode(treiber, INPUT);             // beide wieder freigeben
  pinMode(leser, INPUT);
  return hoch_ok && tief_ok;
}

void setup() {
  Serial.begin(115200);
  pinMode(4, OUTPUT);                  // Blitz-LED aus
  digitalWrite(4, LOW);
  delay(500);
  Serial.println("\n[START] Pin-Brueckentest: Bruecke zwischen zwei der");
  Serial.println("Pins 13/14/15/2 stecken und die passende Zeile beobachten.\n");
}

void loop() {
  for (int a = 0; a < N; a++) {
    for (int b = a + 1; b < N; b++) {
      bool ok = richtung_ok(PINS[a], PINS[b]) &&
                richtung_ok(PINS[b], PINS[a]);
      Serial.printf("%2d<->%-2d: %s\n", PINS[a], PINS[b],
                    ok ? "VERBINDUNG" : "-");
    }
  }
  Serial.println("------------------------------");
  delay(2000);
}
