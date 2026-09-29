/*
 * ESP32-CAM MJPEG-Stream mit Steuerungsendpunkt
 * Gegenstück zu ESP32_CAM_3.py
 *
 * Funktionen:
 *  - MJPEG-Videostream auf Port 81 unter /stream
 *  - Steuerungsendpunkt auf Port 80 unter /control?var=...&val=...
 *    Unterstützte Variablen: awb, wb_mode
 *
 * Benötigte Bibliothek:
 *  - "ESP32 Arduino" Board-Package (esp32 by Espressif Systems)
 *    Board: "AI Thinker ESP32-CAM"
 *
 * WLAN-Zugangsdaten unten eintragen!
 */

#include "esp_camera.h"
#include <WiFi.h>
#include "esp_http_server.h"

// =============================================
//   WLAN-ZUGANGSDATEN – HIER ANPASSEN
// =============================================
// eigenen Netznamen eintragen
const char* WIFI_SSID     = "<WLAN-Name>";
// hier das eigene Kennwort eintragen (im Quelltext steht keines, nur so viele x wie Zeichen)
const char* WIFI_PASSWORT = "xxxxxxxx";

// =============================================
//   KAMERA-PIN-DEFINITION (AI Thinker ESP32-CAM)
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
//   GLOBALE HANDLES
// =============================================
httpd_handle_t stream_httpd  = NULL;
httpd_handle_t control_httpd = NULL;

// =============================================
//   MJPEG-STREAM HANDLER  (/stream, Port 81)
// =============================================
#define PART_BOUNDARY "123456789000000000000987654321"
static const char* STREAM_CONTENT_TYPE =
    "multipart/x-mixed-replace;boundary=" PART_BOUNDARY;
static const char* STREAM_BOUNDARY =
    "\r\n--" PART_BOUNDARY "\r\n";
static const char* STREAM_PART =
    "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

static esp_err_t stream_handler(httpd_req_t* req) {
    camera_fb_t* fb   = NULL;
    esp_err_t    res  = ESP_OK;
    char         part_buf[64];

    res = httpd_resp_set_type(req, STREAM_CONTENT_TYPE);
    if (res != ESP_OK) return res;

    // Wichtig: Kein Content-Length-Header (Chunked-Transfer)
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
    httpd_resp_set_hdr(req, "X-Framerate", "30");

    while (true) {
        fb = esp_camera_fb_get();
        if (!fb) {
            Serial.println("[FEHLER] Kein Kamerabild");
            res = ESP_FAIL;
            break;
        }

        // Boundary senden
        res = httpd_resp_send_chunk(req, STREAM_BOUNDARY, strlen(STREAM_BOUNDARY));
        if (res != ESP_OK) {
            esp_camera_fb_return(fb);
            break;
        }

        // Part-Header senden
        size_t hlen = snprintf(part_buf, sizeof(part_buf), STREAM_PART, fb->len);
        res = httpd_resp_send_chunk(req, part_buf, hlen);
        if (res != ESP_OK) {
            esp_camera_fb_return(fb);
            break;
        }

        // JPEG-Bilddaten senden
        res = httpd_resp_send_chunk(req, (const char*)fb->buf, fb->len);
        esp_camera_fb_return(fb);

        if (res != ESP_OK) break;
    }

    return res;
}

// =============================================
//   STEUERUNGS-HANDLER  (/control, Port 80)
//   Erwartet: /control?var=VARIABLE&val=WERT
//   Unterstützt: awb, wb_mode
// =============================================
static esp_err_t control_handler(httpd_req_t* req) {
    char buf[128];
    size_t buf_len = httpd_req_get_url_query_len(req) + 1;

    if (buf_len <= 1) {
        httpd_resp_send_404(req);
        return ESP_FAIL;
    }

    if (httpd_req_get_url_query_str(req, buf, buf_len) != ESP_OK) {
        httpd_resp_send_404(req);
        return ESP_FAIL;
    }

    char var_str[32] = {0};
    char val_str[16] = {0};

    if (httpd_query_key_value(buf, "var", var_str, sizeof(var_str)) != ESP_OK ||
        httpd_query_key_value(buf, "val", val_str, sizeof(val_str)) != ESP_OK) {
        httpd_resp_send_404(req);
        return ESP_FAIL;
    }

    int val = atoi(val_str);
    sensor_t* s = esp_camera_sensor_get();

    if (!s) {
        httpd_resp_send_500(req);
        return ESP_FAIL;
    }

    Serial.printf("[CONTROL] var=%s val=%d\n", var_str, val);

    if (strcmp(var_str, "awb") == 0) {
        // Automatischer Weißabgleich: 0 = aus, 1 = an
        s->set_whitebal(s, val);

    } else if (strcmp(var_str, "wb_mode") == 0) {
        // Weißabgleich-Preset: 0=Auto, 1=Sunny, 2=Cloudy, 3=Office, 4=Home
        s->set_wb_mode(s, val);

    } else {
        Serial.printf("[CONTROL] Unbekannte Variable: %s\n", var_str);
        httpd_resp_send_404(req);
        return ESP_FAIL;
    }

    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
    httpd_resp_sendstr(req, "OK");
    return ESP_OK;
}

// =============================================
//   WEBSERVER STARTEN
// =============================================
void starte_webserver() {
    // --- Stream-Server auf Port 81 ---
    httpd_config_t stream_cfg = HTTPD_DEFAULT_CONFIG();
    stream_cfg.server_port    = 81;
    stream_cfg.ctrl_port      = 32769;  // interner Kontrollport, muss sich unterscheiden
    stream_cfg.max_uri_handlers = 2;

    httpd_uri_t stream_uri = {
        .uri       = "/stream",
        .method    = HTTP_GET,
        .handler   = stream_handler,
        .user_ctx  = NULL
    };

    if (httpd_start(&stream_httpd, &stream_cfg) == ESP_OK) {
        httpd_register_uri_handler(stream_httpd, &stream_uri);
        Serial.println("[OK] Stream-Server gestartet (Port 81, /stream)");
    } else {
        Serial.println("[FEHLER] Stream-Server konnte nicht gestartet werden!");
    }

    // --- Control-Server auf Port 80 ---
    httpd_config_t ctrl_cfg = HTTPD_DEFAULT_CONFIG();
    ctrl_cfg.server_port    = 80;
    ctrl_cfg.ctrl_port      = 32770;
    ctrl_cfg.max_uri_handlers = 2;

    httpd_uri_t control_uri = {
        .uri       = "/control",
        .method    = HTTP_GET,
        .handler   = control_handler,
        .user_ctx  = NULL
    };

    if (httpd_start(&control_httpd, &ctrl_cfg) == ESP_OK) {
        httpd_register_uri_handler(control_httpd, &control_uri);
        Serial.println("[OK] Control-Server gestartet (Port 80, /control)");
    } else {
        Serial.println("[FEHLER] Control-Server konnte nicht gestartet werden!");
    }
}

// =============================================
//   SETUP
// =============================================
void setup() {
    Serial.begin(115200);
    Serial.println("\n[START] ESP32-CAM wird initialisiert ...");

    // --- Kamera konfigurieren ---
    camera_config_t config;
    config.ledc_channel  = LEDC_CHANNEL_0;
    config.ledc_timer    = LEDC_TIMER_0;
    config.pin_d0        = Y2_GPIO_NUM;
    config.pin_d1        = Y3_GPIO_NUM;
    config.pin_d2        = Y4_GPIO_NUM;
    config.pin_d3        = Y5_GPIO_NUM;
    config.pin_d4        = Y6_GPIO_NUM;
    config.pin_d5        = Y7_GPIO_NUM;
    config.pin_d6        = Y8_GPIO_NUM;
    config.pin_d7        = Y9_GPIO_NUM;
    config.pin_xclk      = XCLK_GPIO_NUM;
    config.pin_pclk      = PCLK_GPIO_NUM;
    config.pin_vsync     = VSYNC_GPIO_NUM;
    config.pin_href      = HREF_GPIO_NUM;
    config.pin_sscb_sda  = SIOD_GPIO_NUM;
    config.pin_sscb_scl  = SIOC_GPIO_NUM;
    config.pin_pwdn      = PWDN_GPIO_NUM;
    config.pin_reset     = RESET_GPIO_NUM;
    config.xclk_freq_hz  = 20000000;
    config.pixel_format  = PIXFORMAT_JPEG;

    // Qualität abhängig von verfügbarem PSRAM
    if (psramFound()) {
        config.frame_size   = FRAMESIZE_VGA;   // 640x480 – passend zum Python-Warte-Frame
        config.jpeg_quality = 10;              // 0–63, niedriger = besser
        config.fb_count     = 2;
        Serial.println("[INFO] PSRAM gefunden – hohe Auflösung aktiv");
    } else {
        config.frame_size   = FRAMESIZE_CIF;   // 400x296 als Fallback
        config.jpeg_quality = 12;
        config.fb_count     = 1;
        Serial.println("[INFO] Kein PSRAM – reduzierte Auflösung");
    }

    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("[FEHLER] Kamera-Initialisierung fehlgeschlagen: 0x%x\n", err);
        Serial.println("Neustart in 5 Sekunden ...");
        delay(5000);
        ESP.restart();
    }
    Serial.println("[OK] Kamera initialisiert");

    // Kamera-Sensor optimieren
    sensor_t* s = esp_camera_sensor_get();
    s->set_whitebal(s, 1);    // AWB ein
    s->set_wb_mode(s, 0);     // Auto-Weißabgleich (wie Python-Start)
    s->set_exposure_ctrl(s, 1);
    s->set_gain_ctrl(s, 1);

    // --- WLAN verbinden ---
    WiFi.begin(WIFI_SSID, WIFI_PASSWORT);
    Serial.print("[WLAN] Verbinde");
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println();
    Serial.print("[OK] WLAN verbunden – IP-Adresse: ");
    Serial.println(WiFi.localIP());
    Serial.println();
    Serial.println("In ESP32_CAM_3.py diese IP eintragen:");
    Serial.print("  IP_ADRESSE = \"");
    Serial.print(WiFi.localIP());
    Serial.println("\"");
    Serial.println();

    // --- Webserver starten ---
    starte_webserver();

    Serial.println("\n[BEREIT] Stream: http://" + WiFi.localIP().toString() + ":81/stream");
    Serial.println("[BEREIT] Control: http://" + WiFi.localIP().toString() + "/control?var=awb&val=1");
}

// =============================================
//   LOOP – WLAN-WATCHDOG
// =============================================
void loop() {
    // WLAN-Verbindung überwachen und bei Verlust neu verbinden
    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[WLAN] Verbindung verloren – versuche Reconnect ...");
        WiFi.disconnect();
        WiFi.begin(WIFI_SSID, WIFI_PASSWORT);

        int versuche = 0;
        while (WiFi.status() != WL_CONNECTED && versuche < 20) {
            delay(500);
            Serial.print(".");
            versuche++;
        }

        if (WiFi.status() == WL_CONNECTED) {
            Serial.println("\n[OK] WLAN wiederhergestellt: " + WiFi.localIP().toString());
        } else {
            Serial.println("\n[FEHLER] Reconnect fehlgeschlagen – Neustart ...");
            delay(1000);
            ESP.restart();
        }
    }

    delay(5000);
}
