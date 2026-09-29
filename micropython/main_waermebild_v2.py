import time
from machine import Pin, I2C, SPI
from ili9341 import Display, color565
from amg88xx import AMG88XX
import network
import ntptime

# =============================================================================
# EINSTELLUNGEN
# =============================================================================

# DYNAMISCHE_FARBSKALA:
#   True  = Farbskala passt sich automatisch (geglaettet) an die aktuellen
#           Messwerte an -- fuer Personenbeobachtung die richtige Wahl.
#   False = Feste Grenzen FESTE_MIN_TEMP / FESTE_MAX_TEMP.
DYNAMISCHE_FARBSKALA = True

FESTE_MIN_TEMP = 20    # nur bei fester Skala: untere Grenze in Grad C
FESTE_MAX_TEMP = 36    # nur bei fester Skala: obere Grenze in Grad C

# MIN_SPANNE: kleinste erlaubte Spreizung der dynamischen Skala in Kelvin.
MIN_SPANNE = 4.0

# GLAETTUNG: 0..1, Traegheit der dynamischen Skala (0.3 = angenehm ruhig).
GLAETTUNG = 0.3

# FARBSKALA_ANZEIGEN: rechts einen Farbbalken mit Max- (oben) und
# Min-Temperatur (unten) einblenden. False = Waermebild ueber volle Breite.
FARBSKALA_ANZEIGEN = True
SKALA_BREITE = 40      # reservierter Streifen rechts in Pixeln

# FELD_PIXEL: Kantenlaenge einer Waermebild-Kachel in Pixeln (8 = fein).
FELD_PIXEL = 8

# FARBPALETTE: "eisen" (schwarz-violett-rot-gelb-weiss, wie echte
# Waermebildkameras) oder "regenbogen" (blau-cyan-gruen-gelb-rot).
FARBPALETTE = "eisen"

# Datum/Uhrzeit in der unteren Leiste anzeigen.
UHR_ANZEIGEN = True

# WLAN fuer den Zeitabgleich per NTP beim Start (leer lassen = kein NTP;
# dann laeuft die interne Uhr, die Thonny beim Verbinden automatisch stellt).
WLAN_SSID = ""
WLAN_PASS = ""

# Zeitzonen-Offset in Stunden: Deutschland Sommerzeit = 2, Winterzeit = 1.
ZEITZONE_OFFSET_H = 2

# =============================================================================
# HARDWARE-INITIALISIERUNG
# =============================================================================

# Hintergrundbeleuchtung des Displays einschalten.
bl = Pin(21, Pin.OUT)
bl.on()

# SPI fuer das Display. 20 MHz: doppelt so schnell wie die urspruenglichen
# 10 MHz. 40 MHz lehnt diese MicroPython-Firmware ab ("clock speed not
# supported" -> Absturz), also dabei bleiben.
spi = SPI(2, baudrate=20000000, sck=Pin(14), mosi=Pin(13))

display = Display(
    spi,
    cs=Pin(15),    # Chip Select
    dc=Pin(2),     # Data/Command
    rst=Pin(4),    # Reset
    width=320,
    height=240,
    rotation=0,
    bgr=False,
    x_offset=0,
    y_offset=0
)

# I2C fuer den AMG8833.
i2c = I2C(0, scl=Pin(22), sda=Pin(27))
sensor = AMG88XX(i2c)

SRC_W, SRC_H = 8, 8

# =============================================================================
# GEOMETRIE: Bildbereich, Skalenstreifen und untere Uhr-Leiste
# =============================================================================
UNTEN_LEISTE = 16 if UHR_ANZEIGEN else 0             # Hoehe der Uhrzeile

if FARBSKALA_ANZEIGEN:
    bild_breite = display.width - SKALA_BREITE   # z.B. 320-40 = 280
else:
    bild_breite = display.width
bild_hoehe = display.height - UNTEN_LEISTE           # z.B. 240-16 = 224

DST_W = bild_breite // FELD_PIXEL      # Kacheln horizontal (280/8 = 35)
DST_H = bild_hoehe // FELD_PIXEL       # Kacheln vertikal   (224/8 = 28)
feld_breite = FELD_PIXEL
feld_hoehe  = FELD_PIXEL

# Lage des Farbbalkens im Skalenstreifen:
BALKEN_X = bild_breite + (SKALA_BREITE - 16) // 2   # 16 px breiter Balken
BALKEN_B = 16
BALKEN_Y = 16                                        # oben Platz fuer Max-Text
BALKEN_H = bild_hoehe - 2 * BALKEN_Y                 # unten Platz fuer Min-Text

# =============================================================================
# FARBPALETTE: einmal vorberechnen (256 Stufen)
# =============================================================================
if FARBPALETTE == "regenbogen":
    STUETZEN = ((0, 0, 128), (0, 0, 255), (0, 255, 255),
                (0, 255, 0), (255, 255, 0), (255, 0, 0))
else:  # "eisen" -- der Klassiker der Waermebildtechnik
    STUETZEN = ((0, 0, 0), (32, 0, 96), (160, 0, 160),
                (255, 64, 0), (255, 200, 0), (255, 255, 255))

PAL_N = 256

def baue_palette():
    """Farbverlauf durch die Stuetzstellen in eine 256er-Tabelle rechnen."""
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
WEISS   = color565(255, 255, 255)

# =============================================================================
# FARBBALKEN einmalig zeichnen (der Verlauf ist statisch, nur die
# Zahlen oben/unten aendern sich im Betrieb)
# =============================================================================
def zeichne_farbbalken():
    # Streifen-Hintergrund schwarz
    display.fill_rectangle(bild_breite, 0, SKALA_BREITE, display.height,
                           SCHWARZ)
    # Verlauf: oben = heiss (Palettenende), unten = kalt (Palettenanfang)
    for i in range(BALKEN_H):
        idx = (BALKEN_H - 1 - i) * (PAL_N - 1) // (BALKEN_H - 1)
        display.fill_rectangle(BALKEN_X, BALKEN_Y + i, BALKEN_B, 1,
                               PALETTE[idx])

if FARBSKALA_ANZEIGEN:
    zeichne_farbbalken()

if UHR_ANZEIGEN:
    # untere Leiste einmal schwarz anlegen
    display.fill_rectangle(0, bild_hoehe, display.width, UNTEN_LEISTE,
                           SCHWARZ)

def zeichne_skalen_text(min_t, max_t):
    """Max-Wert oben, Min-Wert unten am Farbbalken (mit schwarzem
    Hintergrund, damit alte Ziffern ueberschrieben werden)."""
    txt_max = "%.1f" % max_t
    txt_min = "%.1f" % min_t
    # zentriert im Skalenstreifen
    x_max = bild_breite + (SKALA_BREITE - 8 * len(txt_max)) // 2
    x_min = bild_breite + (SKALA_BREITE - 8 * len(txt_min)) // 2
    # alte Textzeilen loeschen (volle Streifenbreite), dann neu schreiben
    display.fill_rectangle(bild_breite, 4, SKALA_BREITE, 8, SCHWARZ)
    display.fill_rectangle(bild_breite, bild_hoehe - 12, SKALA_BREITE, 8,
                           SCHWARZ)
    display.draw_text8x8(x_max, 4, txt_max, WEISS, SCHWARZ)
    display.draw_text8x8(x_min, bild_hoehe - 12, txt_min, WEISS, SCHWARZ)

# =============================================================================
# UHRZEIT: NTP-Abgleich beim Start (optional) und Anzeige unten
# =============================================================================
def zeit_per_ntp_stellen():
    """Einmalig beim Start: WLAN verbinden, Uhr per NTP stellen, WLAN aus.
    Scheitert still -- dann laeuft die interne Uhr weiter."""
    if not WLAN_SSID:
        return
    try:
        wlan = network.WLAN(network.STA_IF)
        wlan.active(True)
        wlan.connect(WLAN_SSID, WLAN_PASS)
        for _ in range(20):                     # bis 10 s warten
            if wlan.isconnected():
                break
            time.sleep(0.5)
        if wlan.isconnected():
            ntptime.settime()                   # stellt RTC auf UTC
            print("Uhr per NTP gestellt.")
        wlan.active(False)                      # WLAN wieder aus
    except Exception as e:
        print("NTP nicht moeglich:", e)

letzte_uhr_sekunde = -1

def zeichne_uhr():
    """Datum und Uhrzeit zentriert in der unteren Leiste; wird nur neu
    gezeichnet, wenn sich die Sekunde geaendert hat."""
    global letzte_uhr_sekunde
    t = time.localtime(time.time() + ZEITZONE_OFFSET_H * 3600)
    if t[5] == letzte_uhr_sekunde:
        return
    letzte_uhr_sekunde = t[5]
    txt = "%02d.%02d.%04d  %02d:%02d:%02d" % (t[2], t[1], t[0],
                                              t[3], t[4], t[5])
    x = (display.width - 8 * len(txt)) // 2
    display.draw_text8x8(x, bild_hoehe + 4, txt, WEISS, SCHWARZ)

if UHR_ANZEIGEN:
    zeit_per_ntp_stellen()

# =============================================================================
# BILINEARE INTERPOLATION 8x8 -> DST_W x DST_H (eine Zeile je Aufruf)
# =============================================================================
def interpoliere_zeile(src, y):
    """Berechnet Zeile y (0..DST_H-1) der interpolierten Matrix."""
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

# =============================================================================
# HAUPTSCHLEIFE
# =============================================================================
# Puffer fuer eine Pixelzeile des Bildbereichs und fuer ein Kachel-Band --
# beide fest angelegt, damit der MicroPython-Speicher nicht fragmentiert.
zeilen_bytes  = bild_breite * 2
zeilen_puffer = bytearray(zeilen_bytes)
band_puffer   = bytearray(zeilen_bytes * feld_hoehe)

# Geglaettete Skalengrenzen (Startwerte egal, pendeln sich sofort ein).
skala_min = 20.0
skala_max = 30.0

while True:
    sensor.refresh()
    buf = sensor._buf
    temps = []

    # Rohdaten (12-Bit signed, 0,25 C/Digit) in Grad Celsius wandeln.
    for i in range(0, len(buf), 2):
        raw = buf[i] | (buf[i+1] << 8)
        if raw & 0x800:
            raw -= 0x1000
        temps.append(raw * 0.25)

    mess_min = min(temps)
    mess_max = max(temps)

    # ---- Skalengrenzen bestimmen ----
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

    # ---- Bild zeilenweise interpolieren, einfaerben und als Band senden ----
    for y in range(DST_H):
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
                zeilen_puffer[p0 + 2*k]     = hb
                zeilen_puffer[p0 + 2*k + 1] = lb
        for k in range(feld_hoehe):
            band_puffer[k * zeilen_bytes:(k + 1) * zeilen_bytes] = zeilen_puffer
        display.block(0, y * feld_hoehe,
                      bild_breite - 1, y * feld_hoehe + feld_hoehe - 1,
                      band_puffer)

    # ---- Skalenbeschriftung und Uhr aktualisieren ----
    if FARBSKALA_ANZEIGEN:
        zeichne_skalen_text(min_t, max_t)
    if UHR_ANZEIGEN:
        zeichne_uhr()

    time.sleep(0.05)
