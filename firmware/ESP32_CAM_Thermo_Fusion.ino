/*
 * ESP32_CAM_Thermo_Fusion.ino
 * AI-Thinker ESP32-CAM + AMG8833 (8x8-Waermebildsensor).
 * Hybride Architektur ("HTTP liefert, Modbus regelt"):
 *
 *   - KAMERABILD: MJPEG-Livestream ueber HTTP, Port 81, /stream
 *     (schnell, direkt vom Browser abspielbar -- kein Modbus-Umweg)
 *   - THERMOWERTE + AUSRICHTUNG: Modbus TCP, Port 502
 *     (64 Temperaturen in einem Telegramm; Offset/Skala/Transparenz/
 *      Spiegelung als Register; Kommando speichert dauerhaft im Flash/NVS)
 *
 * Gegenstueck auf dem PC: thermo_cam_dashboard.py (Ueberlagerung, Regler,
 * Temperaturskala, Datum/Uhrzeit).
 *
 * ---------------------------------------------------------------------------
 * VERDRAHTUNG AMG8833 (I2C, KEINE SD-Karte verwenden!)
 * ---------------------------------------------------------------------------
 *   AI-Thinker ESP32-CAM   AMG8833
 *   GPIO13           <->   SDA
 *   GPIO15           <->   SCL   (der MITTLERE Pin der Reihe 13-15-14!)
 *   3V3              <->   VIN/VCC   (KEINE 5 V -- der AMG8833 ist ein
 *   GND              <->   GND        reiner 3,0..3,6-V-Baustein)
 *   (I2C-Adresse 0x69 oder 0x68 -- wird automatisch gesucht.)
 *   WICHTIG: GPIO14 ist fuer I2C ungeeignet -- die Pull-ups des Sensors
 *   auf der SD-Taktleitung verhindern den Boot (bekanntes CAM-Problem).
 *   Sensor dicht neben dem Kameraobjektiv montieren, gleiche Blickrichtung;
 *   die Feinausrichtung erledigen die Regler im Dashboard.
 *
 * ---------------------------------------------------------------------------
 * MODBUS-REGISTERPLAN (TCP Port 502, eine Verbindung, FC03/04 lesen, FC06 schreiben)
 * ---------------------------------------------------------------------------
 *    9 Blitz-LED GPIO4, 0/1                             (lesen+schreiben)
 *   11 Thermo-Status (1 = AMG8833 gefunden)                       (lesen)
 *   20 Offset X   Pixel, signed, + = nach rechts        (lesen+schreiben)
 *   21 Offset Y   Pixel, signed, + = nach unten         (lesen+schreiben)
 *   22 Skalierung Prozent der Bildbreite (25..400)      (lesen+schreiben)
 *   23 Transparenz Prozent (0..100)                     (lesen+schreiben)
 *   24 Spiegelung Bit0 = horizontal, Bit1 = vertikal    (lesen+schreiben)
 *   25 Kommando: 1 = Reg 20..24 dauerhaft speichern (NVS)    (schreiben)
 *  300..363 Thermowerte Pixel 0..63, signed, 0,25 C/Digit      (lesen)
 * ---------------------------------------------------------------------------
 * Arduino-IDE: Board "AI Thinker ESP32-CAM"; Upload via Adapter/IO0-Bruecke.
 * Serieller Monitor 115200: zeigt IP-Adresse fuer das Dashboard an.
 */

#include "esp_camera.h"
#include <WiFi.h>
#include <Wire.h>
#include <Preferences.h>
#include "esp_http_server.h"

// =============================================
//   EINSTELLUNGEN
// =============================================
// eigenen Netznamen eintragen
const char* WIFI_SSID     = "<WLAN-Name>";
// hier das eigene Kennwort eintragen (im Quelltext steht keines, nur so viele x wie Zeichen)
const char* WIFI_PASSWORT = "xxxxxxxx";

const uint16_t TCP_PORT   = 502;     // Modbus
const uint16_t STREAM_PORT = 81;     // MJPEG-Stream (/stream)

#define I2C_SDA 13                   // AMG8833 SDA (SD-Bus! keine SD-Karte)
#define I2C_SCL 15                   // AMG8833 SCL -- NICHT GPIO14: dessen
                                     // Pull-up blockiert den Boot des
                                     // ESP32-CAM (bekanntes Problem, SD-CLK)

#define BILD_GROESSE   FRAMESIZE_VGA // 640x480; fuer mehr Bildrate: FRAMESIZE_QVGA
#define BILD_QUALITAET 12
#define BLITZ_PIN 4                  // weisse Blitz-LED

// =============================================
//   KAMERA-PINS (AI Thinker ESP32-CAM)
// =============================================
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// =============================================
//   ZUSTAND
// =============================================
WiFiServer server(TCP_PORT);
WiFiClient client;
httpd_handle_t stream_httpd = NULL;

uint16_t blitz = 0;

// Thermosensor
uint8_t  amg_adresse = 0;            // 0 = nicht gefunden
uint16_t thermo_ok   = 0;
int16_t  thermo_raw[64];             // 0,25 C je Digit, signed

// Ausrichtung (aus NVS geladen; Kommando 25 speichert)
Preferences prefs;
int16_t  offset_x   = 0;
int16_t  offset_y   = 0;
uint16_t skala_proz = 100;
uint16_t alpha_proz = 45;
uint16_t spiegel    = 0;

uint8_t  puffer[300];
int      puffer_len = 0;

// =============================================
//   MJPEG-STREAM (wie ESP32_CAM_Stream.ino)
// =============================================
#define PART_BOUNDARY "123456789000000000000987654321"
static const char* STREAM_CONTENT_TYPE =
    "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* STREAM_BOUNDARY = "\r\n--" PART_BOUNDARY "\r\n";
static const char* STREAM_PART =
    "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

static esp_err_t stream_handler(httpd_req_t* req) {
  camera_fb_t* fb = NULL;
  esp_err_t res = httpd_resp_set_type(req, STREAM_CONTENT_TYPE);
  if (res != ESP_OK) return res;
  httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
  char part_buf[64];
  while (true) {
    fb = esp_camera_fb_get();
    if (!fb) { res = ESP_FAIL; break; }
    res = httpd_resp_send_chunk(req, STREAM_BOUNDARY, strlen(STREAM_BOUNDARY));
    if (res == ESP_OK) {
      size_t hlen = snprintf(part_buf, sizeof(part_buf), STREAM_PART, fb->len);
      res = httpd_resp_send_chunk(req, part_buf, hlen);
    }
    if (res == ESP_OK)
      res = httpd_resp_send_chunk(req, (const char*)fb->buf, fb->len);
    esp_camera_fb_return(fb);
    if (res != ESP_OK) break;                 // Browser weg -> Schleife beenden
  }
  return res;
}

void starte_stream_server() {
  httpd_config_t cfg = HTTPD_DEFAULT_CONFIG();
  cfg.server_port = STREAM_PORT;
  cfg.ctrl_port   = 32769;
  httpd_uri_t stream_uri = {
    .uri = "/stream", .method = HTTP_GET,
    .handler = stream_handler, .user_ctx = NULL
  };
  if (httpd_start(&stream_httpd, &cfg) == ESP_OK) {
    httpd_register_uri_handler(stream_httpd, &stream_uri);
    Serial.printf("[OK] MJPEG-Stream auf Port %u, /stream\n", STREAM_PORT);
  } else {
    Serial.println("[FEHLER] Stream-Server startet nicht!");
  }
}

// =============================================
//   AMG8833 (I2C an GPIO13/14)
// =============================================
void amg_schreib(uint8_t reg, uint8_t wert) {
  Wire.beginTransmission(amg_adresse);
  Wire.write(reg);
  Wire.write(wert);
  Wire.endTransmission();
}

void thermo_init() {
  Wire.begin(I2C_SDA, I2C_SCL, 100000);
  const uint8_t kandidaten[2] = {0x69, 0x68};
  for (int k = 0; k < 2; k++) {
    Wire.beginTransmission(kandidaten[k]);
    if (Wire.endTransmission() == 0) { amg_adresse = kandidaten[k]; break; }
  }
  if (!amg_adresse) {
    Serial.printf("[WARNUNG] AMG8833 nicht gefunden (gesucht auf SDA=%d, "
                  "SCL=%d)\n", I2C_SDA, I2C_SCL);
    return;
  }
  amg_schreib(0x00, 0x00);   // Normalmodus
  delay(10);
  amg_schreib(0x01, 0x3F);   // Initial-Reset
  delay(10);
  amg_schreib(0x02, 0x00);   // 10 Bilder/s
  delay(100);
  thermo_ok = 1;
  Serial.printf("[OK] AMG8833 auf I2C-Adresse 0x%02X\n", amg_adresse);
}

void thermo_lesen() {
  if (!thermo_ok) return;
  // 128 Byte Pixeldaten ab Register 0x80, in 4 Bloecken zu 32 Byte
  for (int block = 0; block < 4; block++) {
    Wire.beginTransmission(amg_adresse);
    Wire.write(0x80 + block * 32);
    if (Wire.endTransmission(false) != 0) return;
    if (Wire.requestFrom((int)amg_adresse, 32) != 32) return;
    for (int i = 0; i < 16; i++) {
      int lo = Wire.read();
      int hi = Wire.read();
      int raw = (lo | (hi << 8)) & 0x0FFF;
      if (raw & 0x800) raw -= 0x1000;              // 12-Bit-Vorzeichen
      thermo_raw[block * 16 + i] = (int16_t)raw;   // 0,25 C je Digit
    }
  }
}

// =============================================
//   AUSRICHTUNG: NVS laden/speichern
// =============================================
void ausrichtung_laden() {
  prefs.begin("fusion", false);
  offset_x   = prefs.getShort("ox", 0);
  offset_y   = prefs.getShort("oy", 0);
  skala_proz = prefs.getUShort("sk", 100);
  alpha_proz = prefs.getUShort("al", 45);
  spiegel    = prefs.getUShort("sp", 0);
  Serial.printf("[OK] Ausrichtung geladen: X=%d Y=%d Skala=%u%% "
                "Alpha=%u%% Spiegel=%u\n",
                offset_x, offset_y, skala_proz, alpha_proz, spiegel);
}

void ausrichtung_speichern() {
  prefs.putShort("ox", offset_x);
  prefs.putShort("oy", offset_y);
  prefs.putUShort("sk", skala_proz);
  prefs.putUShort("al", alpha_proz);
  prefs.putUShort("sp", spiegel);
  Serial.println("[OK] Ausrichtung dauerhaft gespeichert (NVS)");
}

// =============================================
//   MODBUS-REGISTERABBILD
// =============================================
uint16_t lese_register(uint16_t adr) {
  switch (adr) {
    case 9:  return blitz;
    case 11: return thermo_ok;
    case 20: return (uint16_t)offset_x;
    case 21: return (uint16_t)offset_y;
    case 22: return skala_proz;
    case 23: return alpha_proz;
    case 24: return spiegel;
    default:
      if (adr >= 300 && adr < 364)
        return (uint16_t)thermo_raw[adr - 300];
      return 0;
  }
}

bool schreibe_register(uint16_t adr, uint16_t wert) {
  switch (adr) {
    case 9:  blitz = wert ? 1 : 0; digitalWrite(BLITZ_PIN, blitz); return true;
    case 20: offset_x = (int16_t)wert; return true;
    case 21: offset_y = (int16_t)wert; return true;
    case 22: if (wert < 25) wert = 25; if (wert > 400) wert = 400;
             skala_proz = wert; return true;
    case 23: if (wert > 100) wert = 100; alpha_proz = wert; return true;
    case 24: spiegel = wert & 3; return true;
    case 25: if (wert == 1) ausrichtung_speichern(); return true;
    default: return false;
  }
}

// =============================================
//   MODBUS TCP
// =============================================
void sende_antwort(const uint8_t* tid, uint8_t unit,
                   const uint8_t* pdu, int pdu_len) {
  uint8_t kopf[7] = { tid[0], tid[1], 0, 0,
                      (uint8_t)((pdu_len + 1) >> 8),
                      (uint8_t)((pdu_len + 1) & 0xFF), unit };
  client.write(kopf, 7);
  client.write(pdu, pdu_len);
}

void bearbeite_pdu(const uint8_t* tid, uint8_t unit,
                   const uint8_t* pdu, int pdu_len) {
  uint8_t antwort[260];
  uint8_t fc = pdu[0];
  if (pdu_len < 5) return;
  uint16_t start = ((uint16_t)pdu[1] << 8) | pdu[2];
  uint16_t wert  = ((uint16_t)pdu[3] << 8) | pdu[4];

  if (fc == 3 || fc == 4) {
    uint16_t anzahl = wert;
    if (anzahl == 0 || anzahl > 125 || start + anzahl > 364) {
      uint8_t aus[2] = { (uint8_t)(fc | 0x80), 2 };
      sende_antwort(tid, unit, aus, 2);
      return;
    }
    antwort[0] = fc;
    antwort[1] = anzahl * 2;
    for (int i = 0; i < anzahl; i++) {
      uint16_t v = lese_register(start + i);
      antwort[2 + 2*i] = v >> 8;
      antwort[3 + 2*i] = v & 0xFF;
    }
    sende_antwort(tid, unit, antwort, 2 + 2 * anzahl);
    return;
  }

  if (fc == 6) {
    if (!schreibe_register(start, wert)) {
      uint8_t aus[2] = { (uint8_t)(fc | 0x80), 2 };
      sende_antwort(tid, unit, aus, 2);
      return;
    }
    sende_antwort(tid, unit, pdu, 5);
    return;
  }

  uint8_t aus[2] = { (uint8_t)(fc | 0x80), 1 };
  sende_antwort(tid, unit, aus, 2);
}

void tcp_poll() {
  if (!client || !client.connected()) {
    WiFiClient neu = server.available();
    if (neu) {
      client = neu;
      puffer_len = 0;
      Serial.println("[TCP] Client verbunden: " + client.remoteIP().toString());
    }
    return;
  }
  while (client.available() && puffer_len < (int)sizeof(puffer))
    puffer[puffer_len++] = client.read();

  while (puffer_len >= 7) {
    int laenge = ((int)puffer[4] << 8) | puffer[5];
    if (laenge < 2 || laenge > 254) { puffer_len = 0; client.stop(); return; }
    if (puffer_len < 6 + laenge) break;
    bearbeite_pdu(puffer, puffer[6], puffer + 7, laenge - 1);
    int rest = puffer_len - (6 + laenge);
    memmove(puffer, puffer + 6 + laenge, rest);
    puffer_len = rest;
  }
}

// =============================================
//   SETUP / LOOP
// =============================================
void setup() {
  Serial.begin(115200);
  Serial.println("\n[START] ESP32-CAM Thermo-Fusion (Stream + Modbus) ...");
  pinMode(BLITZ_PIN, OUTPUT);
  digitalWrite(BLITZ_PIN, LOW);

  ausrichtung_laden();
  thermo_init();

  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk  = XCLK_GPIO_NUM;   config.pin_pclk  = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;  config.pin_href  = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn  = PWDN_GPIO_NUM;   config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  if (psramFound()) {
    config.frame_size   = BILD_GROESSE;
    config.jpeg_quality = BILD_QUALITAET;
    config.fb_count     = 2;
  } else {
    config.frame_size   = FRAMESIZE_CIF;
    config.jpeg_quality = 12;
    config.fb_count     = 1;
  }
  if (esp_camera_init(&config) != ESP_OK) {
    Serial.println("[FEHLER] Kamera-Init fehlgeschlagen, Neustart in 5 s");
    delay(5000);
    ESP.restart();
  }
  sensor_t* s = esp_camera_sensor_get();
  s->set_whitebal(s, 1);
  s->set_exposure_ctrl(s, 1);
  s->set_gain_ctrl(s, 1);
  Serial.println("[OK] Kamera initialisiert");

  WiFi.begin(WIFI_SSID, WIFI_PASSWORT);
  Serial.print("[WLAN] Verbinde");
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println();
  Serial.print("[OK] WLAN verbunden - in thermo_cam_dashboard.py eintragen:  ");
  Serial.println("ESP32CAM_IP = \"" + WiFi.localIP().toString() + "\"");

  starte_stream_server();

  server.begin();
  server.setNoDelay(true);
  Serial.printf("[BEREIT] Modbus TCP auf Port %u; Stream: http://%s:%u/stream\n",
                TCP_PORT, WiFi.localIP().toString().c_str(), STREAM_PORT);
}

void loop() {
  tcp_poll();

  // Thermosensor alle 200 ms auffrischen (Sensor liefert 10 Bilder/s)
  static uint32_t letzte_messung = 0;
  if (millis() - letzte_messung > 200) {
    letzte_messung = millis();
    thermo_lesen();
  }

  // WLAN-Watchdog
  static uint32_t letzter_check = 0;
  if (millis() - letzter_check > 5000) {
    letzter_check = millis();
    if (WiFi.status() != WL_CONNECTED) {
      WiFi.disconnect();
      WiFi.begin(WIFI_SSID, WIFI_PASSWORT);
    }
  }
}
