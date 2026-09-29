#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""referenz_anzeige.py — unabhängige Nachrechnung eines Display-Bildes mit dem Python-Code aus main.py (Display-Board).

Eingabe (JSON auf stdin): {"t": [64 Temperaturen °C], "skala_min": .., "skala_max": ..}
Ausgabe (JSON): {"skala_min", "skala_max", "min_t", "max_t", "kacheln": 28×35 Temperaturen, "idx": 28×35 Palettenindizes, "palette": 256 RGB565}
Die Funktionen interpoliere_zeile und baue_palette sowie die Skalenrechnung sind wörtlich aus main.py übernommen (ohne Display-Aufrufe).
"""
import json, sys

SRC_W, SRC_H = 8, 8
SKALA_BREITE, FELD_PIXEL, UNTEN_LEISTE = 40, 8, 16
bild_breite = 320 - SKALA_BREITE
bild_hoehe = 240 - UNTEN_LEISTE
DST_W = bild_breite // FELD_PIXEL
DST_H = bild_hoehe // FELD_PIXEL
MIN_SPANNE = 4.0
GLAETTUNG = 0.3
STUETZEN = ((0, 0, 0), (32, 0, 96), (160, 0, 160), (255, 64, 0), (255, 200, 0), (255, 255, 255))
PAL_N = 256


def color565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


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


def bild(temps, skala_min, skala_max):
    PALETTE = baue_palette()
    mess_min = min(temps)
    mess_max = max(temps)
    skala_min += (mess_min - skala_min) * GLAETTUNG
    skala_max += (mess_max - skala_max) * GLAETTUNG
    min_t, max_t = skala_min, skala_max
    if max_t - min_t < MIN_SPANNE:
        mitte = (max_t + min_t) / 2
        min_t = mitte - MIN_SPANNE / 2
        max_t = mitte + MIN_SPANNE / 2
    farb_faktor = (PAL_N - 1) / (max_t - min_t)
    kacheln, idx = [], []
    for y in range(DST_H):
        zeile = interpoliere_zeile(temps, y)
        iz = []
        for x in range(DST_W):
            i = int((zeile[x] - min_t) * farb_faktor)
            if i < 0:
                i = 0
            elif i >= PAL_N:
                i = PAL_N - 1
            iz.append(i)
        kacheln.append(zeile)
        idx.append(iz)
    return {"skala_min": skala_min, "skala_max": skala_max, "min_t": min_t, "max_t": max_t, "kacheln": kacheln, "idx": idx, "palette": PALETTE}


if __name__ == "__main__":
    e = json.load(sys.stdin)
    json.dump(bild(e["t"], e["skala_min"], e["skala_max"]), sys.stdout)
