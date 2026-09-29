import time
from machine import Pin, I2C, SPI
from ili9341 import Display, color565
from amg88xx import AMG88XX

# =============================================================================
# EINSTELLUNGEN: Hier kann das Verhalten der Farbskala angepasst werden
# =============================================================================

# DYNAMISCHE_FARBSKALA:
#   True  = Die Farbskala wird automatisch an die jeweils gemessenen Minimal-
#           und Maximaltemperaturen angepasst (dynamische Skalierung).
#   False = Die Farbskala bleibt fest auf die unten eingestellten Werte
#           (FESTE_MIN_TEMP, FESTE_MAX_TEMP) eingestellt.
DYNAMISCHE_FARBSKALA = False

# FESTE_MIN_TEMP und FESTE_MAX_TEMP:
#   Nur relevant, wenn DYNAMISCHE_FARBSKALA = False.
#   Definieren die festen Temperaturgrenzen für die Farbkodierung.
FESTE_MIN_TEMP = 25    # Untere Grenze der Farbskala in Grad Celsius
FESTE_MAX_TEMP = 30    # Obere Grenze der Farbskala in Grad Celsius

# DST_W und DST_H:
#   Zielauflösung für die Anzeige nach Interpolation.
#   Höhere Werte ergeben ein „weicheres“ Bild, benötigen aber mehr Rechenzeit.
DST_W, DST_H = 24, 24  # Beispiel: 32x32 Felder auf dem Display

# =============================================================================
# HARDWARE-INITIALISIERUNG
# =============================================================================

# Hintergrundbeleuchtung des Displays einschalten.
# Ohne diese Zeile bleibt das Display unter Umständen dunkel.
bl = Pin(21, Pin.OUT)
bl.on()

# Initialisierung der SPI-Schnittstelle für das Display.
# Die Pins und der Baudrate-Wert müssen zur Hardware passen.
spi = SPI(2, baudrate=10000000, sck=Pin(14), mosi=Pin(13))

# Initialisierung und Konfiguration des ILI9341-Displays.
# Die Parameter (Pins, Größe, Rotation, etc.) müssen zur Verkabelung passen.
display = Display(
    spi,
    cs=Pin(15),    # Chip Select Pin
    dc=Pin(2),     # Data/Command Pin
    rst=Pin(4),    # Reset Pin
    width=320,     # Display-Breite in Pixeln
    height=240,    # Display-Höhe in Pixeln
    rotation=0,    # Display-Rotation (0 = Standard)
    bgr=False,     # Farbreihenfolge (False = RGB, True = BGR)
    x_offset=0,    # Pixel-Offset X (meist 0)
    y_offset=0     # Pixel-Offset Y (meist 0)
)

# Initialisierung der I2C-Schnittstelle für den AMG8833 Temperatursensor.
# Die Pins müssen mit der Verkabelung übereinstimmen.
i2c = I2C(0, scl=Pin(22), sda=Pin(27))
sensor = AMG88XX(i2c)

# Sensorauflösung (AMG8833 liefert immer 8x8 Werte).
SRC_W, SRC_H = 8, 8

# Berechnung der Größe eines einzelnen Feldes auf dem Display.
# So wird die interpolierte Matrix optimal auf die Displaygröße verteilt.
feld_breite = display.width // DST_W
feld_hoehe = display.height // DST_H

# =============================================================================
# FUNKTION: Temperaturwert in eine RGB-Farbe umwandeln
# =============================================================================
def temp_to_color(temp, min_temp, max_temp):
    """
    Wandelt einen Temperaturwert in eine Farbe um, die von Blau (kalt)
    bis Rot (warm) reicht. Die Skala kann dynamisch (an Messwerte angepasst)
    oder fest (benutzerdefiniert) sein.

    temp:     Temperaturwert, der eingefärbt werden soll
    min_temp: Untere Grenze der Farbskala
    max_temp: Obere Grenze der Farbskala

    Rückgabe: 16-Bit Farbwert für das Display
    """
    # Temperatur auf gültigen Bereich begrenzen (Clamping).
    if temp < min_temp:
        temp = min_temp
    if temp > max_temp:
        temp = max_temp

    # Vermeidung von Division durch Null, falls min_temp == max_temp.
    if max_temp == min_temp:
        ratio = 0
    else:
        # Normierung des Temperaturwerts auf den Bereich 0.0 bis 1.0.
        ratio = (temp - min_temp) / (max_temp - min_temp)

    # Farbverlauf: Blau (kalt) bis Rot (warm).
    # r = Rot-Anteil (steigt mit Temperatur)
    # g = Grün-Anteil (hier immer 0, kann für andere Paletten genutzt werden)
    # b = Blau-Anteil (fällt mit Temperatur)
    r = int(255 * ratio)
    g = 0
    b = int(255 * (1 - ratio))

    # Umwandlung in das vom Display benötigte 16-Bit-Farbformat.
    return color565(r, g, b)

# =============================================================================
# FUNKTION: Bilineare Interpolation einer 8x8-Matrix auf höhere Auflösung
# =============================================================================
def bilinear_interpolate(src, src_w, src_h, dst_w, dst_h):
    """
    Interpoliert eine flache src-Liste (src_w x src_h) auf eine Matrix der
    Größe dst_w x dst_h. Dadurch entsteht ein „weicheres“ Bild, das besser
    aussieht als die grobe 8x8-Matrix des Sensors.

    src:   Eingabewerte (flache Liste mit src_w * src_h Elementen)
    src_w: Breite der Eingabematrix (hier 8)
    src_h: Höhe der Eingabematrix (hier 8)
    dst_w: Zielbreite der Ausgabematrix (z.B. 32)
    dst_h: Zielhöhe der Ausgabematrix (z.B. 32)

    Rückgabe: 2D-Liste (Matrix) mit interpolierten Temperaturwerten
    """
    dst = []  # Ergebnis-Matrix (Liste von Listen)
    for y in range(dst_h):
        # Berechnung der Position in der Quellmatrix (sy: float)
        sy = y * (src_h - 1) / (dst_h - 1)
        y0 = int(sy)                   # Unterer Nachbar (ganzzahlig)
        y1 = min(y0 + 1, src_h - 1)    # Oberer Nachbar (maximal src_h-1)
        wy = sy - y0                   # Gewichtung für Y-Interpolation

        row = []  # Neue Zeile für die Ergebnis-Matrix
        for x in range(dst_w):
            # Berechnung der Position in der Quellmatrix (sx: float)
            sx = x * (src_w - 1) / (dst_w - 1)
            x0 = int(sx)               # Linker Nachbar
            x1 = min(x0 + 1, src_w - 1) # Rechter Nachbar
            wx = sx - x0               # Gewichtung für X-Interpolation

            # Vier Nachbarwerte aus der Quellmatrix holen
            v00 = src[y0 * src_w + x0]  # Links oben
            v01 = src[y0 * src_w + x1]  # Rechts oben
            v10 = src[y1 * src_w + x0]  # Links unten
            v11 = src[y1 * src_w + x1]  # Rechts unten

            # Interpolation in X-Richtung für obere und untere Zeile
            v0 = v00 * (1 - wx) + v01 * wx
            v1 = v10 * (1 - wx) + v11 * wx

            # Interpolation in Y-Richtung zwischen den beiden Zeilen
            value = v0 * (1 - wy) + v1 * wy

            # Ergebnis in die aktuelle Zeile einfügen
            row.append(value)
        # Zeile zur Ergebnis-Matrix hinzufügen
        dst.append(row)
    return dst

# =============================================================================
# HAUPTSCHLEIFE: Sensor auslesen, interpolieren und anzeigen
# =============================================================================
while True:
    # Sensor auffrischen, damit aktuelle Temperaturdaten gelesen werden.
    sensor.refresh()
    buf = sensor._buf  # Rohdaten vom Sensor (Bytearray)
    temps = []         # Liste für Temperaturwerte in Grad Celsius

    # Umwandlung der Rohdaten (je 2 Bytes pro Wert) in Temperaturwerte.
    # Der AMG8833 liefert 64 Werte (8x8), jeweils als 12-Bit signed Integer.
    for i in range(0, len(buf), 2):
        raw = buf[i] | (buf[i+1] << 8)  # 16-Bit Wert aus zwei Bytes zusammensetzen
        if raw & 0x800:                 # Vorzeichenbit prüfen (negative Werte)
            raw -= 0x1000               # Zweierkomplement für negative Werte
        temp_c = raw * 0.25             # Umrechnung auf Grad Celsius (lt. Datenblatt)
        temps.append(temp_c)            # Temperaturwert zur Liste hinzufügen

    # Bestimmung der Farbskala:
    # Je nach Einstellung wird die Skala dynamisch (an aktuelle Messwerte)
    # oder fest (benutzerdefinierte Grenzen) gewählt.
    if DYNAMISCHE_FARBSKALA:
        # Dynamische Skalierung: min/max der aktuellen Messung verwenden.
        min_temp = min(temps)
        max_temp = max(temps)
    else:
        # Feste Skalierung: Werte aus den Einstellungen oben verwenden.
        min_temp = FESTE_MIN_TEMP
        max_temp = FESTE_MAX_TEMP

    # Interpolation der 8x8-Matrix auf die gewünschte Zielauflösung (z.B. 32x32).
    # Dadurch entsteht eine feinere, optisch ansprechendere Darstellung.
    interp_matrix = bilinear_interpolate(temps, SRC_W, SRC_H, DST_W, DST_H)

    # Anzeige der Temperaturmatrix:
    # Für jedes interpolierte Feld wird ein farbiges Rechteck auf das Display gezeichnet.
    for y in range(DST_H):
        for x in range(DST_W):
            temp = interp_matrix[y][x]  # Interpolierter Temperaturwert
            farbe = temp_to_color(temp, min_temp, max_temp)  # Farbbestimmung
            # Zeichnen des Rechtecks an der passenden Position mit der berechneten Farbe.
            display.fill_rectangle(
                x * feld_breite,
                y * feld_hoehe,
                feld_breite,
                feld_hoehe,
                farbe
            )

    # Kurze Pause, um die Anzeige zu aktualisieren und Flackern zu vermeiden.
    time.sleep(0.1)
