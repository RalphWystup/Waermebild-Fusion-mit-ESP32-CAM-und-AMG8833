import time
import json
import network
import ntptime
import socket
from machine import Pin, I2C, SPI
from ili9341 import Display, color565
from amg88xx import AMG88XX

# =============================================================================
# ESP32 mit Display + AMG8833: Waermebild lokal anzeigen UND die 64
# Thermowerte per HTTP/JSON ans Thermo-Fusion-Dashboard liefern (kein
# Modbus -- alles direkt/live). Das Dashboard ueberlagert die Werte mit dem
# Livestream der ESP32-CAM; die Ausrichtung wird HIER auf dem Board
# gespeichert (Datei ausrichtung.json).
#
# HTTP-Schnittstelle (Port 80):
#   GET /thermo                       -> JSON: {"t":[64 Temperaturen in C],
#                                               "einst":{ox,oy,sk,al,sp}}
#   GET /einstellung?ox=..&oy=..&sk=..&al=..&sp=..  -> Ausrichtung setzen
#   GET /speichern                    -> Ausrichtung dauerhaft speichern
# =============================================================================

# ------------------------ EINSTELLUNGEN -------------------------------------
DYNAMISCHE_FARBSKALA = True
FESTE_MIN_TEMP = 20
FESTE_MAX_TEMP = 36
MIN_SPANNE = 4.0
GLAETTUNG = 0.3
FARBSKALA_ANZEIGEN = True
SKALA_BREITE = 40
FELD_PIXEL = 8
FARBPALETTE = "eisen"
UHR_ANZEIGEN = True

# WLAN: noetig fuer die Datenlieferung ans Dashboard (und die Uhr per NTP).
WLAN_SSID = ""            # <-- WLAN-Name eintragen!
WLAN_PASS = ""            # <-- WLAN-Passwort eintragen!
ZEITZONE_OFFSET_H = 2     # Sommerzeit 2, Winterzeit 1

HTTP_PORT = 80
MAX_CLIENTS = 4

# ------------------------ HARDWARE ------------------------------------------
bl = Pin(21, Pin.OUT)
bl.on()

spi = SPI(2, baudrate=20000000, sck=Pin(14), mosi=Pin(13))
display = Display(spi, cs=Pin(15), dc=Pin(2), rst=Pin(4),
                  width=320, height=240, rotation=0, bgr=False,
                  x_offset=0, y_offset=0)

i2c = I2C(0, scl=Pin(22), sda=Pin(27))
sensor = AMG88XX(i2c)

SRC_W, SRC_H = 8, 8

# ------------------------ GEOMETRIE -----------------------------------------
UNTEN_LEISTE = 16 if UHR_ANZEIGEN else 0
bild_breite = display.width - (SKALA_BREITE if FARBSKALA_ANZEIGEN else 0)
bild_hoehe = display.height - UNTEN_LEISTE
DST_W = bild_breite // FELD_PIXEL
DST_H = bild_hoehe // FELD_PIXEL
feld_breite = FELD_PIXEL
feld_hoehe = FELD_PIXEL
BALKEN_X = bild_breite + (SKALA_BREITE - 16) // 2
BALKEN_B = 16
BALKEN_Y = 16
BALKEN_H = bild_hoehe - 2 * BALKEN_Y

# ------------------------ FARBPALETTE ---------------------------------------
if FARBPALETTE == "regenbogen":
    STUETZEN = ((0, 0, 128), (0, 0, 255), (0, 255, 255),
                (0, 255, 0), (255, 255, 0), (255, 0, 0))
else:
    STUETZEN = ((0, 0, 0), (32, 0, 96), (160, 0, 160),
                (255, 64, 0), (255, 200, 0), (255, 255, 255))
PAL_N = 256

def baue_palette():
    pal = []
    segmente = len(STUETZEN) - 1
    for i in range(PAL_N):
        pos = i * segmente / (PAL_N - 1)
        s = int(pos)
        if s >= segmente:
            s = segmente - 1
        t = pos - s
        r = int(STUETZEN[s][0] + (STUETZEN[s+1][0] - STUETZEN[s][0]) * t)
        g = int(STUETZEN[s][1] + (STUETZEN[s+1][1] - STUETZEN[s][1]) * t)
        b = int(STUETZEN[s][2] + (STUETZEN[s+1][2] - STUETZEN[s][2]) * t)
        pal.append(color565(r, g, b))
    return pal

PALETTE = baue_palette()
SCHWARZ = color565(0, 0, 0)
WEISS = color565(255, 255, 255)

# ------------------------ FARBBALKEN / UHR ----------------------------------
def zeichne_farbbalken():
    display.fill_rectangle(bild_breite, 0, SKALA_BREITE, display.height,
                           SCHWARZ)
    for i in range(BALKEN_H):
        idx = (BALKEN_H - 1 - i) * (PAL_N - 1) // (BALKEN_H - 1)
        display.fill_rectangle(BALKEN_X, BALKEN_Y + i, BALKEN_B, 1,
                               PALETTE[idx])

def zeichne_grundschirm():
    """Statische Flaechen (Farbbalken, Uhr-Leiste) anlegen -- beim Start
    und nach dem IP-Startbildschirm."""
    if FARBSKALA_ANZEIGEN:
        zeichne_farbbalken()
    if UHR_ANZEIGEN:
        display.fill_rectangle(0, bild_hoehe, display.width, UNTEN_LEISTE,
                               SCHWARZ)

def zeichne_skalen_text(min_t, max_t):
    txt_max = "%.1f" % max_t
    txt_min = "%.1f" % min_t
    x_max = bild_breite + (SKALA_BREITE - 8 * len(txt_max)) // 2
    x_min = bild_breite + (SKALA_BREITE - 8 * len(txt_min)) // 2
    display.fill_rectangle(bild_breite, 4, SKALA_BREITE, 8, SCHWARZ)
    display.fill_rectangle(bild_breite, bild_hoehe - 12, SKALA_BREITE, 8,
                           SCHWARZ)
    display.draw_text8x8(x_max, 4, txt_max, WEISS, SCHWARZ)
    display.draw_text8x8(x_min, bild_hoehe - 12, txt_min, WEISS, SCHWARZ)

letzte_uhr_sekunde = -1

def zeichne_uhr():
    global letzte_uhr_sekunde
    t = time.localtime(time.time() + ZEITZONE_OFFSET_H * 3600)
    if t[5] == letzte_uhr_sekunde:
        return
    letzte_uhr_sekunde = t[5]
    txt = "%02d.%02d.%04d  %02d:%02d:%02d" % (t[2], t[1], t[0],
                                              t[3], t[4], t[5])
    x = (display.width - 8 * len(txt)) // 2
    display.draw_text8x8(x, bild_hoehe + 4, txt, WEISS, SCHWARZ)

# ------------------------ WLAN ----------------------------------------------
wlan = None

def wlan_start():
    """WLAN verbinden und AN lassen (der Webserver braucht es)."""
    global wlan
    if not WLAN_SSID:
        print("Kein Netzname eingetragen -> nur lokale Anzeige.")
        return
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    try:
        wlan.connect(WLAN_SSID, WLAN_PASS)
    except OSError:
        pass
    print("WLAN: verbinde mit '%s' ..." % WLAN_SSID)
    for _ in range(30):                      # bis 15 s warten
        if wlan.isconnected():
            break
        time.sleep(0.5)
    if wlan.isconnected():
        print("WLAN verbunden, IP:", wlan.ifconfig()[0])
        print("-> in thermo_cam_dashboard.py eintragen: "
              "DISPLAY_IP = \"%s\"" % wlan.ifconfig()[0])
        try:
            ntptime.settime()
        except OSError:
            print("NTP nicht erreichbar (Uhr laeuft trotzdem).")
    else:
        print("WLAN nicht erreichbar -> nur lokale Anzeige.")

# ------------------------ AUSRICHTUNG (Datei) --------------------------------
AUSRICHT_DATEI = "ausrichtung.json"
ausricht = {"ox": 0, "oy": 0, "sk": 100, "al": 45, "sp": 0}
try:
    with open(AUSRICHT_DATEI) as f:
        ausricht.update(json.load(f))
    print("Ausrichtung geladen:", ausricht)
except (OSError, ValueError):
    pass

def ausricht_speichern():
    with open(AUSRICHT_DATEI, "w") as f:
        json.dump(ausricht, f)
    print("Ausrichtung gespeichert:", ausricht)

# ------------------------ MINI-WEBSERVER (HTTP/JSON) --------------------------
thermo_temps = [0.0] * 64                   # aktuelle Temperaturen in Grad C

def http_antwort(körper):
    return ("HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n"
            "Access-Control-Allow-Origin: *\r\nConnection: close\r\n\r\n"
            + körper)

def bearbeite_anfrage(pfad):
    """Pfad inkl. Query auswerten, JSON-Antwortkoerper liefern."""
    if pfad.startswith("/thermo"):
        return json.dumps({"t": [round(t, 2) for t in thermo_temps],
                           "einst": ausricht})
    if pfad.startswith("/einstellung"):
        if "?" in pfad:
            for teil in pfad.split("?", 1)[1].split("&"):
                if "=" in teil:
                    name, wert = teil.split("=", 1)
                    try:
                        wert = int(wert)
                    except ValueError:
                        continue
                    if name in ("ox", "oy"):
                        ausricht[name] = max(-500, min(500, wert))
                    elif name == "sk":
                        ausricht["sk"] = max(25, min(400, wert))
                    elif name == "al":
                        ausricht["al"] = max(0, min(100, wert))
                    elif name == "sp":
                        ausricht["sp"] = wert & 3
        return '{"ok":true}'
    if pfad.startswith("/speichern"):
        ausricht_speichern()
        return '{"ok":true}'
    return '{"fehler":"unbekannter Pfad"}'

srv = None
clients = []                                # [socket, puffer]

def server_start():
    global srv
    if wlan is None or not wlan.isconnected():
        return
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("", HTTP_PORT))
    s.listen(2)
    s.setblocking(False)
    srv = s
    print("Webserver bereit auf Port", HTTP_PORT,
          "( /thermo /einstellung /speichern )")

def schliesse(cl):
    try:
        cl[0].close()
    except OSError:
        pass
    if cl in clients:
        clients.remove(cl)

def http_poll():
    """Nicht blockierend: Verbindungen annehmen, GET-Anfragen beantworten.
    Wird auch waehrend des Zeichnens aufgerufen, damit das Dashboard
    fluessig bedient wird."""
    if srv is None:
        return
    try:
        c, adr = srv.accept()
        c.setblocking(False)
        clients.append([c, b""])
        while len(clients) > MAX_CLIENTS:
            schliesse(clients[0])
    except OSError:
        pass
    for cl in clients[:]:
        try:
            daten = cl[0].recv(512)
        except OSError:
            continue
        if not daten:
            schliesse(cl)
            continue
        cl[1] += daten
        if b"\r\n\r\n" not in cl[1]:        # Anfrage noch unvollstaendig
            if len(cl[1]) > 2048:
                schliesse(cl)
            continue
        zeile = cl[1].split(b"\r\n", 1)[0].decode()
        teile = zeile.split(" ")
        pfad = teile[1] if len(teile) >= 2 else "/"
        try:
            cl[0].send(http_antwort(bearbeite_anfrage(pfad)).encode())
        except OSError:
            pass
        schliesse(cl)                       # eine Anfrage je Verbindung

# ------------------------ INTERPOLATION -------------------------------------
def interpoliere_zeile(src, y):
    sy = y * (SRC_H - 1) / (DST_H - 1)
    y0 = int(sy)
    y1 = y0 + 1 if y0 + 1 < SRC_H else SRC_H - 1
    wy = sy - y0
    zeile = []
    basis0 = y0 * SRC_W
    basis1 = y1 * SRC_W
    for x in range(DST_W):
        sx = x * (SRC_W - 1) / (DST_W - 1)
        x0 = int(sx)
        x1 = x0 + 1 if x0 + 1 < SRC_W else SRC_W - 1
        wx = sx - x0
        v0 = src[basis0 + x0] * (1 - wx) + src[basis0 + x1] * wx
        v1 = src[basis1 + x0] * (1 - wx) + src[basis1 + x1] * wx
        zeile.append(v0 * (1 - wy) + v1 * wy)
    return zeile

# ------------------------ START ----------------------------------------------
wlan_start()
server_start()

def zeige_start_info():
    """IP-Adresse 5 s gross auf dem Display anzeigen -- zum Eintragen in
    thermo_cam_dashboard.py, ganz ohne Thonny."""
    display.fill_rectangle(0, 0, display.width, display.height, SCHWARZ)
    if wlan is not None and wlan.isconnected():
        zeilen = ("THERMO-FUSION",
                  "",
                  "Diese IP im Dashboard",
                  "eintragen:",
                  "",
                  "DISPLAY_IP =",
                  '"%s"' % wlan.ifconfig()[0])
    else:
        zeilen = ("KEIN WLAN!",
                  "",
                  "Netzname+Wort in",
                  "main.py eintragen",
                  "",
                  "(nur lokale Anzeige)")
    y = 60
    for z in zeilen:
        if z:
            x = (display.width - 8 * len(z)) // 2
            display.draw_text8x8(x, y, z, WEISS, SCHWARZ)
        y += 16
    time.sleep(5)
    display.fill_rectangle(0, 0, display.width, display.height, SCHWARZ)

zeige_start_info()
zeichne_grundschirm()

zeilen_bytes = bild_breite * 2
zeilen_puffer = bytearray(zeilen_bytes)
band_puffer = bytearray(zeilen_bytes * feld_hoehe)

skala_min = 20.0
skala_max = 30.0

while True:
    http_poll()

    sensor.refresh()
    buf = sensor._buf
    temps = []
    for i in range(0, len(buf), 2):
        raw = buf[i] | (buf[i+1] << 8)
        if raw & 0x800:
            raw -= 0x1000
        temps.append(raw * 0.25)
        thermo_temps[i // 2] = raw * 0.25   # fuer den Webserver

    mess_min = min(temps)
    mess_max = max(temps)

    if DYNAMISCHE_FARBSKALA:
        skala_min += (mess_min - skala_min) * GLAETTUNG
        skala_max += (mess_max - skala_max) * GLAETTUNG
        min_t, max_t = skala_min, skala_max
        if max_t - min_t < MIN_SPANNE:
            mitte = (max_t + min_t) / 2
            min_t = mitte - MIN_SPANNE / 2
            max_t = mitte + MIN_SPANNE / 2
    else:
        min_t, max_t = FESTE_MIN_TEMP, FESTE_MAX_TEMP

    farb_faktor = (PAL_N - 1) / (max_t - min_t)

    for y in range(DST_H):
        http_poll()                         # Dashboard auch beim Zeichnen bedienen
        zeile = interpoliere_zeile(temps, y)
        for x in range(DST_W):
            idx = int((zeile[x] - min_t) * farb_faktor)
            if idx < 0:
                idx = 0
            elif idx >= PAL_N:
                idx = PAL_N - 1
            farbe = PALETTE[idx]
            hb = farbe >> 8
            lb = farbe & 0xFF
            p0 = x * feld_breite * 2
            for k in range(feld_breite):
                zeilen_puffer[p0 + 2*k] = hb
                zeilen_puffer[p0 + 2*k + 1] = lb
        for k in range(feld_hoehe):
            band_puffer[k * zeilen_bytes:(k + 1) * zeilen_bytes] = zeilen_puffer
        display.block(0, y * feld_hoehe,
                      bild_breite - 1, y * feld_hoehe + feld_hoehe - 1,
                      band_puffer)

    if FARBSKALA_ANZEIGEN:
        zeichne_skalen_text(min_t, max_t)
    if UHR_ANZEIGEN:
        zeichne_uhr()

    time.sleep(0.05)
