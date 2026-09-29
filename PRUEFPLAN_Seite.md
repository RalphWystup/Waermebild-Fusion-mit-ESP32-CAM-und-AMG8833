# Prüfplan — Seite „Wärmebild-Fusion“ (Fassung 1.0, 29.09.2026)

Prof. Dr.-Ing. Ralph Wystup M.Sc. — erstellt mit KI und Agent (Claude Code, Anthropic)

Die Seite trägt die ganze Rechenkette des Versuchs an einer gezeichneten Szene: aus Tasse, Glas und Wand entsteht die
8×8-Matrix, wie der AMG8833 sie sieht (Blickfeld 60°, ein Sensorpixel 72,5 Kamerapixel, Auflösung 0,25 K je Digit,
Parallaxe aus dem Abstand der beiden „Augen“); das Display-Board rechnet sie mit dem Code von `main.py` zu 35 × 28 Kacheln
in der Eisenpalette; das Dashboard legt sie mit den Reglern von `thermo_cam_dashboard.py` über das Kamerabild. Geprüft wird
im echten Browser (Playwright, Chromium) mit `pruefe_seite.mjs`; die Zahlen stehen in `pruefe_seite.json`.

Zwei Wege je Aussage, wo es geht: die Display-Rechnung der Seite gegen eine Nachrechnung in Python (`referenz_anzeige.py`,
die Funktionen wörtlich aus `main.py`), die Sensorwerte gegen die aus der Geometrie berechneten Sichtfelder. Keine Zahl ist
gesetzt, alle sind gerechnet oder gemessen.

| Nr. | Kriterium | Prüfmittel | Schranke | Ergebnis |
|:--|:--|:--|:--|:--|
| W1 | keine Konsolenfehler beim Laden und Bedienen | `pruefe_seite.mjs` (Playwright, Chromium) | keine | ok |
| W2 | Werkzeug vor Text: erster Regler 264 px, Bühne 243 px, Taktknopf 684 px | `pruefe_seite.mjs` | Regler und Bühne unter 500 px, Knopf im ersten Bildschirm unter 900 px | ok |
| W3 | Display-Rechnung der Seite gegen die Python-Nachrechnung aus `main.py`: 980 Kacheln, größte Abweichung 0,0 K, 0 abweichende Palettenindizes, 0 von 256 Palettenwerten verschieden, Skala 16,40 … 37,58 °C | `pruefe_seite.mjs` + `referenz_anzeige.py` | Kacheln ≤ 1e-9 K, Indizes 0, Palette 0, Skala ≤ 1e-9 K | ok |
| W4 | Min/Max an den Gegenständen (0,5 m, kein Rauschen): 6 Sensorpixel liegen rechnerisch ganz auf der Tasse und zeigen je 55,00 °C, 3 ganz auf dem Glas und zeigen je 8,00 °C; Matrix-Max 55,00, Matrix-Min 8,00 | `pruefe_seite.mjs` (Sichtfelder aus `LABOR.sensorzellen()`, Gegenstände aus `LABOR.formen`) | je > 0 Pixel, Abweichung von der eingestellten Temperatur ≤ 1e-12 K | ok |
| W5 | Mittel über die 49 Hintergrundpixel: min 25,00 °C, max 25,50 °C, Mittel 25,1378 °C; 30 Pixel ganz über der Tischkante genau 25,00 °C (eingestellt), 8 ganz auf der Platte genau 25,50 °C (+0,5 K laut Szene), 0 außerhalb; Umgebung auf 28 °C → Δmin = Δmax = ΔMittel = 3,000000 K | `pruefe_seite.mjs` | 0 Pixel außerhalb [25,00; 25,50]; \|Δ − 3 K\| ≤ 1e-9 | ok |
| W6 | Deckung nach rechnerischer Ausrichtung (Größe 91 %, X 28 px, keine Spiegelung): warmer Fleck 18,3 px neben der Tassenmitte | `pruefe_seite.mjs` | kleiner als ein Sensorpixel (72,5 px) | ok |
| W7 | gedrehter Einbau: Spiegelung 3 (beide) aus der Geometrie, Fleck 18,3 px neben der Tassenmitte | `pruefe_seite.mjs` | Spiegelung 3, Abstand < 72,5 px | ok |
| W8 | ohne Spiegelung bei gedrehtem Einbau: Fleck 145 px daneben — die Häkchen sind nötig | `pruefe_seite.mjs` | > 100 px (deutlich mehr als ein Sensorpixel) | ok |
| W9 | Parallaxe: Position X 28 px bei 1 m, 63 px bei 0,3 m, Unterschied 35 px; gerechnet f·b·(1/0,3 − 1) = 35,2 px | `pruefe_seite.mjs` (Geometrie gegen Anzeige) | Abweichung ≤ 1 px (Rundung auf ganze Pixel) | ok |
| W10 | Display gezeichnet: 980 von 980 Kacheln tragen genau die Palettenfarbe der Rechnung; Farbbalken oben rgb(248,252,248) = Palette 255, unten rgb(0,0,0) = Palette 0; 138 helle Bildpunkte im Skalenstreifen (die Zahlen am Balken) | `pruefe_seite.mjs` (Bildpunkte aus dem Canvas) | 980 Kacheln genau, Balkenenden genau, > 0 helle Punkte | ok |
| W11 | Dokumentation in der Seite: Sensor (Grid-EYE), Ausrichtung mit Parallaxe, Vorgeschichte GPIO14, Kapitel 14 „Die Simulation in der Seite“ | `pruefe_seite.mjs` | alle vier Stellen vorhanden | ok |
| W12 | Dokumentation neutralisiert: 2 Fotos des Aufbaus geladen, Platzhalterhinweis vorhanden (Netzname `<WLAN-Name>`, Kennwort als x-Folge, Adressen als `<IP-…>`), keine Adresse im Vierergruppenmuster, kein Kennwortwert | `pruefe_seite.mjs` | gesucht wird der **Platzhalter**, nie der Wert; 0 Adressen, 0 Kennwortwerte, 2 Fotos | ok |
| W13 | Kopfzeile: Fassung 1.0 · 29.09.2026 · Prof. Dr.-Ing. Ralph Wystup M.Sc. — erstellt mit KI und Agent (Claude Code, Anthropic) | `pruefe_seite.mjs` | Fassung, Datum und Name vorhanden | ok |

Die Werte des Aufbaus — Netzname und Adressen im Heimnetz — stehen **nicht** im Erzeuger `erstelle_waermebild_seite.py`
und nicht in `pruefe_seite.mjs`, sondern allein in `neutral_privat.json` neben dem Erzeuger; diese Datei wird nicht
ausgeliefert. Ein Kennwort steht in keiner dieser Dateien: die Sketche tragen so viele `x`, wie der Wert Zeichen hat
(Anweisung des Verfassers vom 29.09.2026) — die Länge bleibt erkennbar, der Wert nicht; das Bauskript zählt die Zeichen
der vorgefundenen Zeichenkette und kennt den Wert ebenfalls nicht.

Stand: 2026-09-29T18:58 · 0 Beanstandung(en). Bildschirmfotos angesehen (Seite mit Reglern und Überlagerung, Szene nach der
rechnerischen Ausrichtung mit dem warmen Fleck auf der Tasse und dem kalten Glas daneben, Display-Board mit Farbbalken
55,1 … 7,9 °C und Uhrzeile, Dokumentationsreiter mit Platzhalterhinweis und beiden Fotos des Aufbaus).
