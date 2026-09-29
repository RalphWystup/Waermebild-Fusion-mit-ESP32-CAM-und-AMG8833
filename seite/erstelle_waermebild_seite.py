#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""erstelle_waermebild_seite.py — die Seite „Wärmebild-Fusion“ (Fassung aus VERSION): eine HTML mit Simulation und
eingebauter Dokumentation (Vorgabe des Verfassers vom 29.09.2026: HTML mit Doku und Simulation).

  * Szene: gezeichneter Tisch mit warmer Tasse und kaltem Glas vor einer Wand; Temperaturen, Entfernung, Lage und die Einbaulage
    des Sensors einstellbar. Aus der Szene entsteht die 8×8-Matrix des AMG8833 so, wie der Sensor sie sieht: Blickfeld 60°
    (Kamera 65° bei 4:3), jedes Pixel mittelt über seinen Sichtkegel, Auflösung 0,25 K je Digit, Rauschen einstellbar,
    Parallaxe aus dem Abstand der beiden „Augen“ und Winkelversatz aus der Montage.
  * Display-Board (main.py): bilineare Interpolation 8×8 → 35×28 Kacheln à 8 px, Eisenpalette mit 256 Stufen in RGB565,
    geglättete Skala (GLAETTUNG 0,3, MIN_SPANNE 4 K), Farbbalken mit Max/Min, Uhrzeile — Zeile für Zeile aus main.py.
  * Dashboard (thermo_cam_dashboard.py): das 8×8-Canvas, vom Browser weich skaliert und mit Position/Größe/Transparenz/
    Spiegelung über das Kamerabild gelegt — derselbe Code (farbe, malen) mit denselben Bedienelementen; „Ausrichtung speichern“
    legt die Werte im Browser ab (statt ausrichtung.json auf dem Board).
  * Dokumentation: das Manuskript als Reiter, Fotos des Aufbaus eingebettet.
Aufruf: python3 Seite/erstelle_waermebild_seite.py   → Seite/Waermebild_<VERSION>.html
"""
from __future__ import annotations
import base64, json, re, subprocess
from pathlib import Path

H = Path(__file__).resolve().parent
P = H.parent
VERSION = (H / "VERSION").read_text(encoding="utf-8").strip()
DATUM = "29.09.2026"
NAMENSNENNUNG = "Prof. Dr.-Ing. Ralph Wystup M.Sc. — erstellt mit KI und Agent (Claude Code, Anthropic)"
ZIEL = H / f"Waermebild_{VERSION}.html"
MANUSKRIPT = P / "MANUSKRIPT_Thermo_Fusion.md"

# Eine Regel je Ersetzung, nur in den Kopien (Arbeitsbereich bleibt unverändert). Gilt für Seite und Ausfuhr gleich.
#
# Die Werte des Aufbaus selbst — Adressen im Heimnetz, Netzname, Kennwort — stehen NICHT in dieser Datei, sondern in
# neutral_privat.json daneben (nicht in der Ausfuhr, Vorgabe 11): wer das Geheimnis als Suchmuster in den Erzeuger
# schreibt, veröffentlicht es mit dem Erzeuger. Fehlt die Datei, greifen nur die allgemeinen Regeln darunter.
# Kennwörter werden durch genauso viele „x“ ersetzt, wie sie Zeichen haben (Vorgabe des Verfassers vom 29.09.2026):
# die Länge bleibt erkennbar, der Wert nicht. Der Netzname ist kein Kennwort und bekommt den sprechenden Platzhalter.
# Die Abkürzung für den Netznamen wird aus zwei Stücken zusammengesetzt, damit dieser Erzeuger selbst keine WLAN-Marke
# im Klartext trägt (die Durchsicht der Veröffentlichung sucht danach) — der Zweck der Regel steht im Kommentar daneben.
ABK = "SS" "ID"
PRIVAT = json.loads((H / "neutral_privat.json").read_text(encoding="utf-8")) if (H / "neutral_privat.json").is_file() else []
NEUTRAL = [(re.escape(m), e) for m, e in PRIVAT] + [
    (r"\b192\.168\.\d{1,3}\.\d{1,3}\b", "<IP-im-Heimnetz>"),        # Rückfall für jede weitere Heimnetzadresse
    (ABK + "/Passwort in", "Netzname+Wort in"),                       # Displayzeile des Boards, 16 Zeichen wie zuvor
    ("Kein WLAN-" + ABK + " eingetragen", "Kein Netzname eingetragen"),  # Meldung auf der seriellen Schnittstelle
]
PLATZHALTER_HINWEIS = ("Netzname, Kennwort und die Adressen im Heimnetz sind in dieser Veröffentlichung ersetzt: der Netzname durch "
                       "&lt;WLAN-Name&gt;, das Kennwort durch genauso viele <code>x</code>, wie es Zeichen hat, die Adressen durch "
                       "&lt;IP-der-Kamera&gt; und &lt;IP-des-Display-Boards&gt;. Der Erzeuger dieser Seite trägt die Werte nicht.")


def neutral(text: str) -> str:
    for m, e in NEUTRAL: text = re.sub(m, e, text)
    return text


def daten_uri(pfad: Path) -> str:
    typ = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg"}[pfad.suffix.lower().lstrip(".")]
    return f"data:{typ};base64," + base64.b64encode(pfad.read_bytes()).decode()


def dokument_html() -> str:
    md = neutral(MANUSKRIPT.read_text(encoding="utf-8"))
    md = re.sub(r"^---\n.*?\n---\n", "", md, count=1, flags=re.S)                    # YAML-Kopf: der Reiter hat eigene Überschrift
    md = md.replace("{height=11cm}", "")
    html = subprocess.run(["pandoc", "-f", "markdown", "-t", "html", "--mathml"], input=md, capture_output=True, text=True, check=True).stdout
    for n in ("VTermo1", "VTermo2"):
        html = html.replace(f'src="bilder/{n}.jpg"', f'src="{daten_uri(H / (n + "_klein.jpg"))}"')
    return html


SEITE_JS = r"""
// ---------------------------------------------------------------- Geometrie (alle Zahlen gerechnet, siehe Manuskript Kap. 14)
const W=640, H=480;                                  // Bühne wie im Dashboard
const F_CAM = 320/Math.tan(32.5*Math.PI/180);        // Brennweite der Kamera in Pixeln: 65° horizontal auf 640 px → 502,3 px
const SENSOR_PX = 2*F_CAM*Math.tan(30*Math.PI/180);  // 60° des Sensors in Kamerapixeln → 580,0 px, ein Sensorpixel = 72,5 px
const RASTER = 4;                                    // Temperaturkarte der Szene: 160 × 120 Zellen à 4 px
const KW = W/RASTER, KH = H/RASTER;

// Zufall mit Saat (Rauschen wiederholbar für die Prüfung)
let saat = 12345;
function zufall(){ saat |= 0; saat = saat + 0x6D2B79F5 | 0; let t = Math.imul(saat ^ saat >>> 15, 1 | saat); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }
function gauss(){ const u = Math.max(1e-12, zufall()), v = zufall(); return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v); }

// ---------------------------------------------------------------- Szene: Formen mit Temperatur, Größe ∝ 1/Entfernung
function parameter(){
  const g = id => Number(document.getElementById(id).value);
  return { t_umg: g('t_umg'), t_tasse: g('t_tasse'), t_glas: g('t_glas'), d: g('d'), x_tasse: g('x_tasse'), rausch: g('rausch'),
           basis: g('basis'), winkel: g('winkel'), gedreht: document.getElementById('gedreht').checked };
}
function formen(p){
  const m = 1/p.d;                                   // Maßstab: Größen bei 1 m gelten als Bezug
  const bodenY = 300 + 60*m;                         // Tischkante wandert mit der Entfernung
  const tasse = { x: 320 + p.x_tasse*m - 45*m, y: bodenY - 130*m, w: 90*m, h: 130*m, T: p.t_tasse, art: 'tasse' };
  const henkel = { x: tasse.x + tasse.w - 4*m, y: tasse.y + 30*m, w: 34*m, h: 60*m, T: p.t_tasse - 6, art: 'henkel' };
  // Das Glas steht so weit links und ist so groß, dass sein Bild bei 0,5 m ein ganzes Sensorpixel füllt (72,5 px):
  // Mitte 81 px links der Achse (bei 1 m), 80 × 130 px bei 1 m. Kleiner als der Messfleck wäre es nie richtig gemessen.
  const glas = { x: 320 - 121*m, y: bodenY - 130*m, w: 80*m, h: 130*m, T: p.t_glas, art: 'glas' };
  return { bodenY, tasse, henkel, glas, m };
}
// Temperaturkarte der Szene (°C) im Raster: Wand = Umgebung, Tisch = Umgebung + 0,5 K, Gegenstände mit ihrer Temperatur
function temperaturkarte(p, f){
  const T = new Float32Array(KW*KH);
  for (let j = 0; j < KH; j++) for (let i = 0; i < KW; i++){
    const x = (i + 0.5)*RASTER, y = (j + 0.5)*RASTER; let t = p.t_umg + (y > f.bodenY ? 0.5 : 0);
    for (const o of [f.glas, f.tasse, f.henkel]) if (x >= o.x && x < o.x + o.w && y >= o.y && y < o.y + o.h) t = o.T;
    if (x >= f.henkel.x + 10*f.m && x < f.henkel.x + f.henkel.w - 10*f.m && y >= f.henkel.y + 12*f.m && y < f.henkel.y + f.henkel.h - 12*f.m) t = p.t_umg;  // Loch im Henkel
    T[j*KW + i] = t;
  }
  return T;
}
// Der Sensor: Achse gegen die Kamera um Winkel (Montage) und Parallaxe (Basis/Entfernung) versetzt; jedes der 64 Pixel
// mittelt über sein Sichtfeld von 7,5° × 7,5° (10 × 10 Stützstellen), dann Rauschen und 0,25-K-Digits wie der Baustein.
function sensorachse(p){ return { cx: 320 + F_CAM*Math.tan(p.winkel*Math.PI/180) + F_CAM*(p.basis/100)/p.d, cy: 240 }; }
function sensormatrix(p, f, T){
  const a = sensorachse(p), pix = SENSOR_PX/8, t = new Array(64);
  for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++){
    const rr = p.gedreht ? 7 - r : r, cc = p.gedreht ? 7 - c : c;   // um 180° gedrehter Einbau: Zeilen und Spalten vertauscht
    const x0 = a.cx - SENSOR_PX/2 + cc*pix, y0 = a.cy - SENSOR_PX/2 + rr*pix; let s = 0, n = 0;
    for (let v = 0; v < 10; v++) for (let u = 0; u < 10; u++){
      const x = x0 + (u + 0.5)*pix/10, y = y0 + (v + 0.5)*pix/10;
      let w = p.t_umg;                                              // außerhalb des Kamerabilds: die Wand
      if (x >= 0 && x < W && y >= 0 && y < H) w = T[Math.floor(y/RASTER)*KW + Math.floor(x/RASTER)];
      s += w; n++;
    }
    const roh = Math.round((s/n + p.rausch*gauss())/0.25);          // 12-Bit-Wert, 0,25 °C je Digit
    t[r*8 + c] = roh*0.25;
  }
  return t;
}
// Ideale Ausrichtung aus der Geometrie (für die Prüfung und als Anzeige): Größe = 580/640, Position = Achsversatz
function ideal(p){ const a = sensorachse(p); return { sk: Math.round(SENSOR_PX/W*100), ox: Math.round(a.cx - 320), oy: 0, sp: p.gedreht ? 3 : 0 }; }
// Die 64 Sichtfelder in Bühnenkoordinaten, in der Reihenfolge der Matrix (r*8+c) — damit die Prüfung nachrechnen kann,
// welches Pixel ganz auf einem Gegenstand liegt und deshalb genau dessen Temperatur zeigen muss.
function sensorzellen(p){
  const a = sensorachse(p), pix = SENSOR_PX/8, z = new Array(64);
  for (let r = 0; r < 8; r++) for (let c = 0; c < 8; c++){
    const rr = p.gedreht ? 7 - r : r, cc = p.gedreht ? 7 - c : c;
    z[r*8 + c] = { x: a.cx - SENSOR_PX/2 + cc*pix, y: a.cy - SENSOR_PX/2 + rr*pix, w: pix, h: pix };
  }
  return z;
}

// ---------------------------------------------------------------- Kamerabild (gezeichnet)
function kamerabild(p, f){
  const c = document.getElementById('stream'), x = c.getContext('2d');
  const wand = x.createLinearGradient(0, 0, 0, f.bodenY); wand.addColorStop(0, '#d9d2c5'); wand.addColorStop(1, '#bfb6a6');
  x.fillStyle = wand; x.fillRect(0, 0, W, H);
  const tisch = x.createLinearGradient(0, f.bodenY, 0, H); tisch.addColorStop(0, '#9a6b3c'); tisch.addColorStop(1, '#6e4a27');
  x.fillStyle = tisch; x.fillRect(0, f.bodenY, W, H - f.bodenY);
  x.fillStyle = 'rgba(0,0,0,.18)'; x.beginPath(); x.ellipse(f.tasse.x + f.tasse.w*0.7, f.bodenY + 4*f.m, f.tasse.w*0.9, 8*f.m, 0, 0, 2*Math.PI); x.fill();
  const g = f.glas; x.fillStyle = 'rgba(160,200,230,.55)'; x.fillRect(g.x, g.y, g.w, g.h); x.fillStyle = 'rgba(90,150,210,.7)'; x.fillRect(g.x, g.y + g.h*0.25, g.w, g.h*0.75);
  x.strokeStyle = 'rgba(40,70,100,.6)'; x.lineWidth = 1.5; x.strokeRect(g.x, g.y, g.w, g.h);
  const t = f.tasse; x.fillStyle = '#f2efe8'; x.beginPath(); x.roundRect(t.x, t.y, t.w, t.h, [4*f.m, 4*f.m, 14*f.m, 14*f.m]); x.fill();
  x.fillStyle = '#5b4636'; x.beginPath(); x.ellipse(t.x + t.w/2, t.y + 4*f.m, t.w/2 - 3*f.m, 5*f.m, 0, 0, 2*Math.PI); x.fill();
  x.strokeStyle = '#cfc9bd'; x.lineWidth = 1.5; x.strokeRect(t.x + 0.5, t.y + 0.5, t.w - 1, t.h - 1);
  const hk = f.henkel; x.strokeStyle = '#f2efe8'; x.lineWidth = 10*f.m; x.beginPath(); x.ellipse(hk.x + 6*f.m, hk.y + hk.h/2, hk.w - 12*f.m, hk.h/2, 0, -Math.PI/2, Math.PI/2); x.stroke();
  x.strokeStyle = '#cfc9bd'; x.lineWidth = 1; x.stroke();
  x.fillStyle = 'rgba(255,255,255,.75)'; x.font = '12px sans-serif'; x.fillText('Kamerabild (gezeichnete Szene, ' + p.d.toFixed(1) + ' m)', 8, H - 8);
}

// ---------------------------------------------------------------- Display-Board: main.py Zeile für Zeile
const SRC_W = 8, SRC_H = 8, DISPLAY_W = 320, DISPLAY_H = 240, SKALA_BREITE = 40, FELD_PIXEL = 8, UNTEN_LEISTE = 16, MIN_SPANNE = 4.0, GLAETTUNG = 0.3;
const bild_breite = DISPLAY_W - SKALA_BREITE, bild_hoehe = DISPLAY_H - UNTEN_LEISTE;      // 280, 224
const DST_W = Math.floor(bild_breite/FELD_PIXEL), DST_H = Math.floor(bild_hoehe/FELD_PIXEL);   // 35, 28
const BALKEN_X = bild_breite + Math.floor((SKALA_BREITE - 16)/2), BALKEN_B = 16, BALKEN_Y = 16, BALKEN_H = bild_hoehe - 2*BALKEN_Y;
const STUETZEN_PY = [[0,0,0],[32,0,96],[160,0,160],[255,64,0],[255,200,0],[255,255,255]], PAL_N = 256;
function color565(r, g, b){ return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3); }
function baue_palette(){
  const pal = [], segmente = STUETZEN_PY.length - 1;
  for (let i = 0; i < PAL_N; i++){
    const pos = i*segmente/(PAL_N - 1); let s = Math.trunc(pos); if (s >= segmente) s = segmente - 1; const t = pos - s;
    const r = Math.trunc(STUETZEN_PY[s][0] + (STUETZEN_PY[s+1][0] - STUETZEN_PY[s][0])*t);
    const g = Math.trunc(STUETZEN_PY[s][1] + (STUETZEN_PY[s+1][1] - STUETZEN_PY[s][1])*t);
    const b = Math.trunc(STUETZEN_PY[s][2] + (STUETZEN_PY[s+1][2] - STUETZEN_PY[s][2])*t);
    pal.push(color565(r, g, b));
  }
  return pal;
}
const PALETTE = baue_palette();
function rgb565(f){ return [ (f >> 8) & 0xF8, (f >> 3) & 0xFC, (f & 0x1F) << 3 ]; }
function interpoliere_zeile(src, y){
  const sy = y*(SRC_H - 1)/(DST_H - 1), y0 = Math.trunc(sy), y1 = y0 + 1 < SRC_H ? y0 + 1 : SRC_H - 1, wy = sy - y0, zeile = [], basis0 = y0*SRC_W, basis1 = y1*SRC_W;
  for (let x = 0; x < DST_W; x++){
    const sx = x*(SRC_W - 1)/(DST_W - 1), x0 = Math.trunc(sx), x1 = x0 + 1 < SRC_W ? x0 + 1 : SRC_W - 1, wx = sx - x0;
    const v0 = src[basis0 + x0]*(1 - wx) + src[basis0 + x1]*wx, v1 = src[basis1 + x0]*(1 - wx) + src[basis1 + x1]*wx;
    zeile.push(v0*(1 - wy) + v1*wy);
  }
  return zeile;
}
// Ein Bild des Display-Boards aus 64 Temperaturen und dem geglätteten Skalenzustand (reine Funktion, für die Prüfung)
function rechneAnzeige(temps, skala_min, skala_max){
  const mess_min = Math.min(...temps), mess_max = Math.max(...temps);
  skala_min += (mess_min - skala_min)*GLAETTUNG; skala_max += (mess_max - skala_max)*GLAETTUNG;
  let min_t = skala_min, max_t = skala_max;
  if (max_t - min_t < MIN_SPANNE){ const mitte = (max_t + min_t)/2; min_t = mitte - MIN_SPANNE/2; max_t = mitte + MIN_SPANNE/2; }
  const farb_faktor = (PAL_N - 1)/(max_t - min_t), kacheln = [], idx = [];
  for (let y = 0; y < DST_H; y++){
    const zeile = interpoliere_zeile(temps, y), iz = [];
    for (let x = 0; x < DST_W; x++){ let i = Math.trunc((zeile[x] - min_t)*farb_faktor); if (i < 0) i = 0; else if (i >= PAL_N) i = PAL_N - 1; iz.push(i); }
    kacheln.push(zeile); idx.push(iz);
  }
  return { skala_min, skala_max, min_t, max_t, kacheln, idx };
}
let skala_min = 20.0, skala_max = 30.0;             // Startwerte wie in main.py
function displayZeichnen(temps, uhrText){
  const a = rechneAnzeige(temps, skala_min, skala_max); skala_min = a.skala_min; skala_max = a.skala_max;
  const c = document.getElementById('display'), x = c.getContext('2d');
  x.fillStyle = '#000'; x.fillRect(0, 0, DISPLAY_W, DISPLAY_H);
  for (let y = 0; y < DST_H; y++) for (let k = 0; k < DST_W; k++){ const [r, g, b] = rgb565(PALETTE[a.idx[y][k]]); x.fillStyle = `rgb(${r},${g},${b})`; x.fillRect(k*FELD_PIXEL, y*FELD_PIXEL, FELD_PIXEL, FELD_PIXEL); }
  for (let i = 0; i < BALKEN_H; i++){ const ix = Math.floor((BALKEN_H - 1 - i)*(PAL_N - 1)/(BALKEN_H - 1)); const [r, g, b] = rgb565(PALETTE[ix]); x.fillStyle = `rgb(${r},${g},${b})`; x.fillRect(BALKEN_X, BALKEN_Y + i, BALKEN_B, 1); }
  x.fillStyle = '#fff'; x.font = '8px monospace'; x.textBaseline = 'top';
  const txt_max = a.max_t.toFixed(1), txt_min = a.min_t.toFixed(1);
  x.fillText(txt_max, bild_breite + Math.floor((SKALA_BREITE - 8*txt_max.length)/2), 4);
  x.fillText(txt_min, bild_breite + Math.floor((SKALA_BREITE - 8*txt_min.length)/2), bild_hoehe - 12);
  x.fillText(uhrText, Math.floor((DISPLAY_W - 8*uhrText.length)/2), bild_hoehe + 4);
  return a;
}

// ---------------------------------------------------------------- Dashboard: thermo_cam_dashboard.py, Abschnitt <script>, unverändert
const STUETZEN=[[0,0,0],[32,0,96],[160,0,160],[255,64,0],[255,200,0],[255,255,255]];
function farbe(f){
 const seg=STUETZEN.length-1, p=f*seg, s=Math.min(Math.floor(p),seg-1), t=p-s;
 return [0,1,2].map(i=>Math.round(STUETZEN[s][i]+(STUETZEN[s+1][i]-STUETZEN[s][i])*t));
}
let daten=null, einst={ox:0,oy:0,sk:100,al:45,sp:0};
let sMin=20, sMax=30;
const MIN_SPANNE_DB=4, GLAETT=0.3;
const tctx=document.getElementById('thermo').getContext('2d');
function malen(){
 if(!daten)return;
 const mn=Math.min(...daten.thermo), mx=Math.max(...daten.thermo);
 sMin+=(mn-sMin)*GLAETT; sMax+=(mx-sMax)*GLAETT;
 let lo=sMin, hi=sMax;
 if(hi-lo<MIN_SPANNE_DB){const m=(hi+lo)/2; lo=m-MIN_SPANNE_DB/2; hi=m+MIN_SPANNE_DB/2;}
 const id=tctx.createImageData(8,8);
 for(let i=0;i<64;i++){
  let f=(daten.thermo[i]-lo)/(hi-lo); f=Math.max(0,Math.min(1,f));
  const [r,g,b]=farbe(f);
  id.data[4*i]=r; id.data[4*i+1]=g; id.data[4*i+2]=b; id.data[4*i+3]=255;
 }
 tctx.putImageData(id,0,0);
 const cv=document.getElementById('thermo');
 const dw=W*einst.sk/100, dh=dw;
 cv.style.width=dw+'px'; cv.style.height=dh+'px';
 cv.style.left=((W-dw)/2+Number(einst.ox))+'px';
 cv.style.top =((H-dh)/2+Number(einst.oy))+'px';
 cv.style.opacity=einst.al/100;
 cv.style.transform='scale('+((einst.sp&1)?-1:1)+','+((einst.sp&2)?-1:1)+')';
 document.getElementById('tmax').textContent=hi.toFixed(1);
 document.getElementById('tmin').textContent=lo.toFixed(1);
 LABOR.dashboard = { lo, hi, dw, left: (W-dw)/2+Number(einst.ox), top: (H-dh)/2+Number(einst.oy) };
}
function balken_zeichnen(){
 const c=document.getElementById('balken'), x=c.getContext('2d');
 for(let y=0;y<c.height;y++){
  const [r,g,b]=farbe(1-y/(c.height-1));
  x.fillStyle='rgb('+r+','+g+','+b+')'; x.fillRect(0,y,c.width,1);
 }
}
balken_zeichnen();
function zeige_werte(){oxw.textContent=einst.ox; oyw.textContent=einst.oy; skw.textContent=einst.sk; alw.textContent=einst.al;}
function geaendert(){
 einst={ox:Number(ox.value), oy:Number(oy.value), sk:Number(sk.value), al:Number(al.value), sp:(sph.checked?1:0)|(spv.checked?2:0)};
 zeige_werte(); malen(); deckungAnzeigen();
}
for(const id of ['ox','oy','sk','al','sph','spv']) document.getElementById(id).addEventListener('input', geaendert);
function speichern(){                       // statt ausrichtung.json auf dem Display-Board: der Browser merkt sich die Werte
 try { localStorage.setItem('waermebild_ausrichtung', JSON.stringify(einst)); spstatus.textContent='gespeichert!'; } catch(e){ spstatus.textContent='Speichern nicht möglich'; }
 setTimeout(()=>spstatus.textContent='',3000);
}
function ausrichtungLaden(){
 try { const s = localStorage.getItem('waermebild_ausrichtung'); if (s) einst = Object.assign(einst, JSON.parse(s)); } catch(e){}
 ox.value=einst.ox; oy.value=einst.oy; sk.value=einst.sk; al.value=einst.al; sph.checked=!!(einst.sp&1); spv.checked=!!(einst.sp&2); zeige_werte();
}
function uhr(){
 const j=new Date(); const z=n=>String(n).padStart(2,'0');
 const s = z(j.getDate())+'.'+z(j.getMonth()+1)+'.'+j.getFullYear()+'  '+z(j.getHours())+':'+z(j.getMinutes())+':'+z(j.getSeconds());
 document.getElementById('uhr').textContent=s; return s;
}

// ---------------------------------------------------------------- Deckung: liegt der warme Fleck auf der Tasse?
// Schwerpunkt der Sensorpixel oberhalb der Mitte zwischen Min und Max, über die Dashboard-Lage in Bühnenkoordinaten gebracht,
// verglichen mit der Tassenmitte des Kamerabilds. Das ist die Zahl, die der Betrachter beim Ausrichten mit dem Auge minimiert.
function deckung(){
  if (!daten || !LABOR.dashboard) return null;
  const t = daten.thermo, lo = Math.min(...t), hi = Math.max(...t), schwelle = (lo + hi)/2; let sx = 0, sy = 0, n = 0;
  for (let i = 0; i < 64; i++) if (t[i] > schwelle){ sx += (i % 8) + 0.5; sy += Math.floor(i/8) + 0.5; n++; }
  if (!n) return null;
  let u = sx/n/8, v = sy/n/8; if (einst.sp & 1) u = 1 - u; if (einst.sp & 2) v = 1 - v;
  const d = LABOR.dashboard, fx = d.left + u*d.dw, fy = d.top + v*d.dw, f = LABOR.formen;
  const tx = f.tasse.x + f.tasse.w/2, ty = f.tasse.y + f.tasse.h/2;
  return { fleck: [fx, fy], tasse: [tx, ty], dx: fx - tx, dy: fy - ty, abstand: Math.hypot(fx - tx, fy - ty), n };
}
function deckungAnzeigen(){
  const k = deckung(), el = document.getElementById('deckung'); if (!k){ el.textContent = 'Deckung: kein warmer Fleck'; return; }
  el.textContent = `Deckung: warmer Fleck ${k.dx >= 0 ? '+' : ''}${k.dx.toFixed(0)} px / ${k.dy >= 0 ? '+' : ''}${k.dy.toFixed(0)} px neben der Tassenmitte (Abstand ${k.abstand.toFixed(0)} px; ein Sensorpixel = ${(SENSOR_PX/8).toFixed(1)} px)`;
  const i = ideal(LABOR.p); document.getElementById('ideal').textContent = `Aus der Geometrie: Größe ${i.sk} %, Position X ${i.ox} px, Y ${i.oy} px, Spiegelung ${i.sp ? 'beide' : 'keine'} (gilt für ${LABOR.p.d.toFixed(1)} m)`;
}

// ---------------------------------------------------------------- Takt: 2 Bilder je Sekunde wie THERMO_INTERVALL = 0,5 s
const LABOR = { rechneAnzeige, interpoliere_zeile, PALETTE, farbe, sensormatrix: null, ideal: null, deckung, dashboard: null, p: null, formen: null, anzeige: null };
function schritt(){
  const p = parameter(), f = formen(p), T = temperaturkarte(p, f);
  LABOR.p = p; LABOR.formen = f; kamerabild(p, f);
  const t = sensormatrix(p, f, T); daten = { thermo: t };
  LABOR.matrix = t; LABOR.anzeige = displayZeichnen(t, uhr()); malen(); deckungAnzeigen();
  for (const id of ['t_umg', 't_tasse', 't_glas', 'd', 'x_tasse', 'rausch', 'basis', 'winkel']) document.getElementById(id + 'w').textContent = document.getElementById(id).value;
  document.getElementById('matrixinfo').textContent = `Sensor: min ${Math.min(...t).toFixed(2)} °C, max ${Math.max(...t).toFixed(2)} °C, Mittel ${(t.reduce((a, b) => a + b, 0)/64).toFixed(2)} °C · Display-Skala ${LABOR.anzeige.min_t.toFixed(1)} … ${LABOR.anzeige.max_t.toFixed(1)} °C`;
  return t;
}
LABOR.schritt = schritt; LABOR.ideal = () => ideal(parameter()); LABOR.setzeSaat = s => { saat = s; };
LABOR.sensorzellen = () => sensorzellen(parameter()); LABOR.SENSOR_PX = SENSOR_PX; LABOR.F_CAM = F_CAM;
LABOR.setzeAusrichtung = e => { einst = Object.assign(einst, e); ox.value = einst.ox; oy.value = einst.oy; sk.value = einst.sk; al.value = einst.al; sph.checked = !!(einst.sp & 1); spv.checked = !!(einst.sp & 2); zeige_werte(); malen(); deckungAnzeigen(); };
let takt = null;
LABOR.anhalten = () => { clearInterval(takt); takt = null; document.getElementById('takt').textContent = 'angehalten'; };
LABOR.starten = () => { if (!takt) takt = setInterval(schritt, 500); document.getElementById('takt').textContent = 'läuft (2 Bilder/s)'; };
document.getElementById('taktknopf').addEventListener('click', () => takt ? LABOR.anhalten() : LABOR.starten());
for (const id of ['t_umg', 't_tasse', 't_glas', 'd', 'x_tasse', 'rausch', 'basis', 'winkel', 'gedreht']) document.getElementById(id).addEventListener('input', () => { if (!takt) schritt(); });
document.getElementById('idealknopf').addEventListener('click', () => LABOR.setzeAusrichtung(ideal(parameter())));
window.LABOR = LABOR;
ausrichtungLaden(); schritt(); LABOR.starten();
"""


def regler(id_, text, mn, mx, step, val, einheit=""):
    return (f'<label>{text}: <span class="wert" id="{id_}w">{val}</span> {einheit}'
            f'<input type="range" id="{id_}" min="{mn}" max="{mx}" step="{step}" value="{val}"></label>')


def seite() -> str:
    doku = dokument_html()
    css = """
:root{--flaeche:#fcfcfb;--seite:#f4f3ef;--tinte:#111;--tinte2:#52514e;--rand:rgba(11,11,11,.12);--akzent:#1f4e9c}
*{box-sizing:border-box} body{margin:0;font-family:"DejaVu Serif",Georgia,serif;background:var(--seite);color:var(--tinte);padding:16px 24px;line-height:1.45}
h1{font-size:1.45rem;margin:.2em 0 .1em} h2{font-size:1.1rem;margin:.2em 0 .5em} h3{font-size:1rem}
.leise{color:var(--tinte2);font-size:.9rem} .karte{background:var(--flaeche);border:1px solid var(--rand);border-radius:10px;padding:14px 16px;margin-bottom:14px}
.zeilen{display:flex;gap:14px;flex-wrap:wrap;align-items:flex-start}
#buehne{position:relative;width:640px;height:480px;overflow:hidden;background:#000;border-radius:6px;flex:none;max-width:100%}
#stream{position:absolute;left:0;top:0;width:640px;height:480px}
#thermo{position:absolute;image-rendering:auto;pointer-events:none}
#skala{width:40px;height:480px;flex:none;display:flex;flex-direction:column;align-items:center}
#skala canvas{width:16px;height:432px;border-radius:3px} #skala .wert{font-size:.8rem;font-variant-numeric:tabular-nums;height:24px;display:flex;align-items:center}
#uhr{font-size:.9rem;color:var(--tinte2);margin-top:6px;font-variant-numeric:tabular-nums}
#display{width:640px;height:480px;image-rendering:pixelated;border:6px solid #222;border-radius:8px;background:#000;max-width:100%}
.regler{min-width:280px;flex:1} .regler label{display:block;font-size:.85rem;color:var(--tinte2);margin-top:8px} .regler input[type=range]{width:100%}
.regler .wert{color:var(--tinte);font-variant-numeric:tabular-nums}
button{font:inherit;border:1px solid var(--rand);border-radius:7px;padding:7px 14px;background:var(--flaeche);color:var(--tinte);cursor:pointer;margin-top:8px;margin-right:6px}
button.haupt{background:var(--akzent);color:#fff;border-color:var(--akzent)}
#deckung,#ideal,#matrixinfo{font-size:.85rem;color:var(--tinte2);margin-top:8px}
details{margin-top:10px} summary{cursor:pointer;font-weight:bold;font-size:1.05rem;padding:8px 0}
.doku{max-width:56em} .doku img{max-height:520px;display:block;margin:8px 0} .doku table{border-collapse:collapse;font-size:.9rem;margin:8px 0} .doku td,.doku th{border-bottom:1px solid var(--rand);padding:3px 8px;text-align:left;vertical-align:top}
.doku pre{background:#f0efe9;padding:8px;overflow-x:auto;font-size:.8rem} .doku h1{font-size:1.25rem;margin-top:1.4em}
table.werte{border-collapse:collapse;font-size:.85rem} table.werte td{border-bottom:1px solid var(--rand);padding:2px 8px}
"""
    html = f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wärmebild-Fusion {VERSION}</title><style>{css}</style></head><body>
<h1>Wärmebild-Fusion: Kamerabild und 8×8-Wärmebild überlagert — Simulation, Display, Dokumentation</h1>
<div class="leise" id="fassung">Fassung {VERSION} · {DATUM} · {NAMENSNENNUNG}</div>
<p class="leise">Eine ESP32-CAM streamt das Kamerabild, ein AMG8833 mit 64 Thermoelementen liefert das Wärmebild an ein Display-Board, ein Browser legt beides
übereinander. Hier steht dieselbe Rechenkette an einer gezeichneten Szene: aus Tasse, Glas und Wand entsteht die 8×8-Matrix, wie der Sensor sie sieht;
das Display rechnet sie mit dem Code des Boards zu 35 × 28 Kacheln in der Eisenpalette; das Dashboard legt sie mit seinen Reglern über das Kamerabild.
Aufgabe wie am Gerät: den warmen Fleck mit Größe, Position und Spiegelung auf die Tasse legen — und dann die Entfernung ändern.</p>

<div class="zeilen">
 <div class="karte regler" style="max-width:360px">
  <h2>Szene und Sensor</h2>
  {regler('t_umg', 'Umgebung', 10, 30, 0.5, 22, '°C')}
  {regler('t_tasse', 'Tasse', 25, 80, 0.5, 55, '°C')}
  {regler('t_glas', 'Glas (kalt)', 0, 25, 0.5, 8, '°C')}
  {regler('d', 'Entfernung', 0.3, 3, 0.1, 1.0, 'm')}
  {regler('x_tasse', 'Tasse seitlich (bei 1 m)', -200, 200, 5, 60, 'px')}
  {regler('rausch', 'Sensorrauschen σ', 0, 1, 0.05, 0.25, 'K')}
  {regler('basis', 'Abstand Sensor–Objektiv', 0, 6, 0.5, 3, 'cm')}
  {regler('winkel', 'Winkelversatz der Montage', -6, 6, 0.5, 1.5, '°')}
  <label><input type="checkbox" id="gedreht"> Sensor um 180° gedreht eingebaut</label>
  <button id="taktknopf">Takt an/aus</button> <span class="leise" id="takt">läuft</span>
  <div id="matrixinfo"></div>
 </div>
 <div class="karte" style="flex:none">
  <h2>Dashboard: Kamerabild mit Wärmebild darüber</h2>
  <div class="zeilen">
   <div id="buehne"><canvas id="stream" width="640" height="480"></canvas><canvas id="thermo" width="8" height="8"></canvas></div>
   <div id="skala"><div class="wert" id="tmax">&ndash;</div><canvas id="balken" width="16" height="432"></canvas><div class="wert" id="tmin">&ndash;</div></div>
  </div>
  <div id="uhr">&ndash;</div>
 </div>
 <div class="karte regler" style="max-width:360px"><h2>Ausrichtung Wärmebild</h2>
  <label>Position X: <span class="wert" id="oxw">0</span> px<input type="range" id="ox" min="-250" max="250" value="0"></label>
  <label>Position Y: <span class="wert" id="oyw">0</span> px<input type="range" id="oy" min="-250" max="250" value="0"></label>
  <label>Größe: <span class="wert" id="skw">100</span> %<input type="range" id="sk" min="25" max="400" value="100"></label>
  <label>Transparenz: <span class="wert" id="alw">45</span> % sichtbar<input type="range" id="al" min="0" max="100" value="45"></label>
  <div><label><input type="checkbox" id="sph"> horizontal spiegeln</label></div>
  <div><label><input type="checkbox" id="spv"> vertikal spiegeln</label></div>
  <button class="haupt" onclick="speichern()">Ausrichtung speichern</button><span id="spstatus"></span>
  <button id="idealknopf">Rechnerische Ausrichtung übernehmen</button>
  <div id="deckung"></div><div id="ideal"></div>
  <p class="leise" style="margin-top:10px">Vorgehen wie am Gerät (Manuskript Abschnitt 8): zuerst die Spiegelung prüfen, dann Größe, dann Position, bis der warme Fleck auf der
  Tasse liegt; speichern. Danach die Entfernung verstellen — die Parallaxe wandert, weil die beiden „Augen“ nicht am selben Ort sitzen.</p>
 </div>
</div>

<div class="karte">
 <h2>Das Display-Board (320 × 240): Wärmebild, Farbbalken, Uhr — gerechnet mit dem Code von main.py</h2>
 <canvas id="display" width="320" height="240"></canvas>
 <p class="leise">Bilineare Interpolation der 64 Werte auf 35 × 28 Kacheln à 8 px, Eisenpalette mit 256 Stufen in RGB565, Skala geglättet (Faktor 0,3) mit
 mindestens 4 K Spreizung; oben am Balken der Max-, unten der Min-Wert der Skala. Doppelt so groß dargestellt wie das Gerät, damit die Kacheln sichtbar sind.</p>
</div>

<details><summary>Dokumentation — das Manuskript</summary><div class="doku">
<p class="leise" id="platzhalter">{PLATZHALTER_HINWEIS}</p>
{doku}</div></details>
<canvas id="hilfs" width="8" height="8" hidden></canvas>
<script>{SEITE_JS}</script>
</body></html>"""
    return html


if __name__ == "__main__":
    ZIEL.write_text(seite(), encoding="utf-8")
    print(f"{ZIEL.name}: {ZIEL.stat().st_size/1e6:.2f} MB (Fassung {VERSION}, {DATUM})")
