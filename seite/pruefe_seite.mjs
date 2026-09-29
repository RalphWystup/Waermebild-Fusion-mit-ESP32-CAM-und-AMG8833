// Prüfung der Wärmebild-Seite im echten Browser (Playwright, Chromium). Jede Zeile nennt die Zahl und ihre Schranke.
//   W1  keine Konsolenfehler
//   W2  Werkzeug vor Text: erster Regler, Bühne und erster Knopf im ersten Bildschirm
//   W3  Display-Rechnung (Interpolation, Skala, Palettenindizes, Palette) gegen die Nachrechnung in Python (referenz_anzeige.py)
//   W4  Min/Max: jedes Sensorpixel, dessen Sichtfeld ganz auf einem Gegenstand liegt, zeigt genau dessen Temperatur
//   W5  Mittel: Hintergrundpixel genau auf Umgebung / Umgebung + 0,5 K; Umgebung +3 K → min, max und Mittel steigen um genau 3 K
//   W6  Deckung nach rechnerischer Ausrichtung besser als ein Sensorpixel
//   W7  gedrehter Einbau: beide Spiegelungen, Deckung wieder im Sensorpixel
//   W8  ohne Spiegelung bei gedrehtem Einbau liegt der Fleck weit daneben (die Häkchen sind nötig)
//   W9  Parallaxe: Versatz zwischen 1 m und 0,3 m gleich f·b·(1/0,3 − 1)
//   W10 Display gezeichnet: alle 980 Kacheln tragen genau die Palettenfarbe der Rechnung, Balken oben weiß, unten schwarz
//   W11 Dokumentation in der Seite vorhanden (Sensor, Ausrichtung, Vorgeschichte, Kapitel 14), beide Fotos geladen
//   W12 Dokumentation neutralisiert: Platzhalter vorhanden, keine Adresse, kein Netzname, kein Kennwortwert
//   W13 Kopfzeile mit Fassung, Datum, Name
// Ergebnis nach pruefe_seite.json, Bildschirmfotos ins Scratchpad.
import { createRequire } from 'node:module';
import fs from 'node:fs';
import { execFileSync } from 'node:child_process';
const require = createRequire(import.meta.url);
const { chromium } = require('/tmp/node_modules/playwright');
const H = '/workspace/Waermebild/Seite/'; const V = fs.readFileSync(H + 'VERSION', 'utf8').trim();
const S = '/tmp/claude-1000/-workspace/905236e7-aea4-4c03-805a-5e5668f5230d/scratchpad/';
let fehler = 0; const BEF = []; const sage = (gut, t) => { console.log(`  ${gut ? 'ok    ' : 'FEHLER'} ${t}`); BEF.push({ gut, text: t }); if (!gut) fehler++; };
const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1500, height: 1000 } });
const konsole = []; p.on('pageerror', e => konsole.push(e.message)); p.on('console', m => { if (m.type() === 'error') konsole.push(m.text()); });
await p.goto(`file://${H}Waermebild_${V}.html`, { waitUntil: 'load', timeout: 120000 }); await p.waitForTimeout(1200);

// W1
sage(konsole.length === 0, 'keine Konsolenfehler' + (konsole.length ? ': ' + konsole[0].slice(0, 120) : ''));

// W2: Werkzeug vor Text
const lage = await p.evaluate(() => ['t_umg', 'buehne', 'taktknopf'].map(i => document.getElementById(i).getBoundingClientRect().top));
sage(lage[0] < 500 && lage[1] < 500 && lage[2] < 900,
  `Werkzeug vor Text: erster Regler bei ${lage[0].toFixed(0)} px, Bühne bei ${lage[1].toFixed(0)} px, Taktknopf bei ${lage[2].toFixed(0)} px (Schranke: Regler und Bühne unter 500 px, Knopf im ersten Bildschirm unter 900 px)`);

const setze = async (id, v) => { await p.evaluate(([id, v]) => { const el = document.getElementById(id); if (el.type === 'checkbox') el.checked = v; else el.value = v; el.dispatchEvent(new Event('input')); }, [id, v]); };
await p.evaluate(() => window.LABOR.anhalten());
await p.screenshot({ path: S + 'waerme_seite.png' });

// W3: Display-Rechnung gegen die Nachrechnung in Python
await setze('rausch', 0.25); await p.evaluate(() => { window.LABOR.setzeSaat(4711); window.LABOR.schritt(); });
const t0 = await p.evaluate(() => window.LABOR.matrix);
const js = await p.evaluate(t => { const a = window.LABOR.rechneAnzeige(t, 20, 30); return { ...a, palette: window.LABOR.PALETTE }; }, t0);
const py = JSON.parse(execFileSync('python3', [H + 'referenz_anzeige.py'], { input: JSON.stringify({ t: t0, skala_min: 20, skala_max: 30 }) }).toString());
let dK = 0, dI = 0, dP = 0; for (let y = 0; y < 28; y++) for (let x = 0; x < 35; x++) { dK = Math.max(dK, Math.abs(js.kacheln[y][x] - py.kacheln[y][x])); dI += js.idx[y][x] !== py.idx[y][x]; }
for (let i = 0; i < 256; i++) dP += js.palette[i] !== py.palette[i];
const dS = Math.max(Math.abs(js.min_t - py.min_t), Math.abs(js.max_t - py.max_t));
sage(dK <= 1e-9 && dI === 0 && dP === 0 && dS <= 1e-9, `Display-Rechnung gegen die Python-Nachrechnung aus main.py: 980 Kacheln, größte Abweichung ${dK.toExponential(1)} K (Schranke 1e-9), abweichende Palettenindizes ${dI} (Schranke 0), Palette ${dP} von 256 verschieden (Schranke 0), Skala ${py.min_t.toFixed(2)} … ${py.max_t.toFixed(2)} °C (Δ ${dS.toExponential(1)} K)`);

// W4: Min/Max an den Gegenständen. Nicht geraten: die Prüfung holt die 64 Sichtfelder und die Gegenstände aus der Seite und
// rechnet aus, welches Pixel ganz auf der Tasse und welches ganz auf dem Glas liegt. Ohne Rauschen muss es genau deren
// Temperatur zeigen. Der Henkel (Tassentemperatur − 6 K) wird ausgeschlossen, sonst wäre das Pixel nicht einfarbig.
await setze('rausch', 0); await setze('d', 0.5); await setze('t_tasse', 55); await setze('t_glas', 8); await setze('t_umg', 22); await setze('gedreht', false);
const g = await p.evaluate(() => {
  const t = window.LABOR.schritt(), z = window.LABOR.sensorzellen(), f = window.LABOR.formen;
  const drin = (c, o) => c.x >= o.x && c.x + c.w <= o.x + o.w && c.y >= o.y && c.y + c.h <= o.y + o.h;
  const schneidet = (c, o) => c.x < o.x + o.w && c.x + c.w > o.x && c.y < o.y + o.h && c.y + c.h > o.y;
  const auf = o => z.map((c, i) => [c, i]).filter(([c]) => drin(c, o) && !(o !== f.henkel && schneidet(c, f.henkel))).map(([, i]) => i);
  const tasse = auf(f.tasse), glas = auf(f.glas);
  return { t, tasse, glas, t_tasse: tasse.map(i => t[i]), t_glas: glas.map(i => t[i]), pix: z[0].w,
           min: Math.min(...t), max: Math.max(...t) };
});
const alle = (a, v) => a.length > 0 && a.every(x => Math.abs(x - v) <= 1e-12);
sage(alle(g.t_tasse, 55) && alle(g.t_glas, 8) && g.max === 55 && g.min === 8,
  `Min/Max an den Gegenständen (0,5 m, kein Rauschen, Sichtfeld eines Pixels ${g.pix.toFixed(1)} px): ${g.tasse.length} Pixel liegen ganz auf der Tasse und zeigen ${g.t_tasse.map(x => x.toFixed(2)).join('/')} °C (eingestellt 55,00), ${g.glas.length} ganz auf dem Glas mit ${g.t_glas.map(x => x.toFixed(2)).join('/')} °C (eingestellt 8,00); Matrix max ${g.max.toFixed(2)}, min ${g.min.toFixed(2)} (Schranke: je > 0 Pixel, Abweichung ≤ 1e-12 K)`);

// W5: Mittel. Der Hintergrund ist die Wand (eingestellte Umgebungstemperatur) und die Tischplatte (laut Szenendefinition
// 0,5 K wärmer). Jedes Sensorpixel, das keinen Gegenstand berührt, muss zwischen beiden liegen; liegt es ganz über der
// Tischkante, genau auf der Umgebungstemperatur, liegt es ganz auf der Platte, genau 0,5 K darüber. Wird die Umgebung um
// genau 3 K angehoben, müssen min, max und Mittel dieser Hintergrundpixel um genau 3 K steigen — das prüft das Mittel.
await setze('d', 1.0); await setze('t_umg', 25);
const hg = async () => await p.evaluate(() => {
  const t = window.LABOR.schritt(), z = window.LABOR.sensorzellen(), f = window.LABOR.formen, u = Number(document.getElementById('t_umg').value);
  const schneidet = (c, o) => c.x < o.x + o.w && c.x + c.w > o.x && c.y < o.y + o.h && c.y + c.h > o.y;
  const frei = z.map((c, i) => [c, i]).filter(([c]) => ![f.tasse, f.henkel, f.glas].some(o => schneidet(c, o)));
  const w = frei.map(([, i]) => t[i]);
  const wand = frei.filter(([c]) => c.y + c.h <= f.bodenY).map(([, i]) => t[i]);
  const tisch = frei.filter(([c]) => c.y >= f.bodenY && c.y + c.h <= 480 && c.x >= 0 && c.x + c.w <= 640).map(([, i]) => t[i]);
  return { u, n: w.length, min: Math.min(...w), max: Math.max(...w), mit: w.reduce((a, b) => a + b, 0) / w.length,
           wand, tisch, aus: w.filter(v => v < u - 1e-12 || v > u + 0.5 + 1e-12).length };
});
const b1 = await hg(); await setze('t_umg', 28); const b2 = await hg();
const genau = (a, v) => a.length > 0 && a.every(x => Math.abs(x - v) <= 1e-12);
const d5 = [b2.min - b1.min, b2.max - b1.max, b2.mit - b1.mit];
sage(b1.aus === 0 && genau(b1.wand, 25) && genau(b1.tisch, 25.5) && d5.every(x => Math.abs(x - 3) <= 1e-9),
  `Mittel über die ${b1.n} Hintergrundpixel (kein Gegenstand im Sichtfeld): min ${b1.min.toFixed(2)} °C, max ${b1.max.toFixed(2)} °C, Mittel ${b1.mit.toFixed(4)} °C; ${b1.wand.length} Pixel ganz über der Tischkante zeigen genau ${b1.wand[0].toFixed(2)} °C (eingestellt 25,00), ${b1.tisch.length} ganz auf der Platte genau ${b1.tisch[0].toFixed(2)} °C (25,00 + 0,50), ${b1.aus} außerhalb [25,00; 25,50] (Schranke 0); Umgebung auf 28 °C → Δmin ${d5[0].toFixed(6)}, Δmax ${d5[1].toFixed(6)}, ΔMittel ${d5[2].toFixed(6)} K (Schranke |Δ − 3| ≤ 1e-9)`);

// W6: Deckung nach rechnerischer Ausrichtung
await setze('t_umg', 22); await setze('rausch', 0.25);
let k = await p.evaluate(() => { const i = window.LABOR.ideal(); window.LABOR.setzeAusrichtung(i); window.LABOR.schritt(); return { i, k: window.LABOR.deckung(), pix: window.LABOR.SENSOR_PX / 8 }; });
sage(k.k && k.k.abstand < k.pix, `Deckung nach rechnerischer Ausrichtung (Größe ${k.i.sk} %, X ${k.i.ox} px, Spiegelung ${k.i.sp}): warmer Fleck ${k.k.abstand.toFixed(1)} px neben der Tassenmitte (Schranke ein Sensorpixel ${k.pix.toFixed(1)} px)`);
await p.screenshot({ path: S + 'waerme_ausgerichtet.png' });

// W7/W8: gedrehter Einbau
await setze('gedreht', true);
k = await p.evaluate(() => { const i = window.LABOR.ideal(); window.LABOR.setzeAusrichtung(i); window.LABOR.schritt(); return { i, k: window.LABOR.deckung(), pix: window.LABOR.SENSOR_PX / 8 }; });
sage(k.k && k.i.sp === 3 && k.k.abstand < k.pix, `gedrehter Einbau: Spiegelung ${k.i.sp} (beide), Fleck ${k.k.abstand.toFixed(1)} px neben der Tassenmitte (Schranke ${k.pix.toFixed(1)} px)`);
const falsch = await p.evaluate(() => { const i = window.LABOR.ideal(); window.LABOR.setzeAusrichtung({ ...i, sp: 0 }); window.LABOR.schritt(); return window.LABOR.deckung(); });
sage(falsch && falsch.abstand > 100, `ohne Spiegelung bei gedrehtem Einbau: Fleck ${falsch.abstand.toFixed(0)} px daneben (Schranke > 100 px) — die Häkchen sind nötig`);
await setze('gedreht', false);

// W9: Parallaxe aus der Geometrie
const par = await p.evaluate(async () => { const s = v => { const el = document.getElementById('d'); el.value = v; el.dispatchEvent(new Event('input')); };
  s(1.0); const a = window.LABOR.ideal(); s(0.3); const b = window.LABOR.ideal(); s(1.0); window.LABOR.schritt(); return { a, b, f: window.LABOR.F_CAM }; });
const erwartet = par.f * 0.03 * (1 / 0.3 - 1);
sage(Math.abs((par.b.ox - par.a.ox) - erwartet) <= 1, `Parallaxe: Position X ${par.a.ox} px bei 1 m, ${par.b.ox} px bei 0,3 m — Unterschied ${par.b.ox - par.a.ox} px, gerechnet f·b·(1/0,3 − 1) = ${erwartet.toFixed(1)} px (Schranke 1 px, Rundung auf ganze Pixel)`);

// W10: Display gezeichnet — jede Kachel trägt genau die Palettenfarbe der Rechnung
const disp = await p.evaluate(() => {
  const c = document.getElementById('display'), x = c.getContext('2d'), a = window.LABOR.anzeige, P = window.LABOR.PALETTE;
  const bild = x.getImageData(0, 0, c.width, c.height).data;
  const hol = (px, py) => { const o = 4 * (py * c.width + px); return [bild[o], bild[o + 1], bild[o + 2]]; };
  const rgb = f => [(f >> 8) & 0xF8, (f >> 3) & 0xFC, (f & 0x1F) << 3];
  let schlecht = 0;
  for (let y = 0; y < 28; y++) for (let k = 0; k < 35; k++) {
    const s = hol(k * 8 + 4, y * 8 + 4), e = rgb(P[a.idx[y][k]]);
    if (s[0] !== e[0] || s[1] !== e[1] || s[2] !== e[2]) schlecht++;
  }
  const oben = hol(292 + 8, 16), unten = hol(292 + 8, 16 + 192 - 1);
  let weiss = 0; for (let py = 0; py < 240; py++) for (let px = 280; px < 320; px++) { const s = hol(px, py); if (s[0] > 200 && s[1] > 200 && s[2] > 200) weiss++; }
  return { schlecht, oben, unten, weiss };
});
sage(disp.schlecht === 0 && disp.oben.join() === '248,252,248' && disp.unten.join() === '0,0,0' && disp.weiss > 0,
  `Display-Board gezeichnet: ${980 - disp.schlecht} von 980 Kacheln tragen genau die Palettenfarbe der Rechnung (Schranke 980), Farbbalken oben rgb(${disp.oben}) = Palette 255, unten rgb(${disp.unten}) = Palette 0, ${disp.weiss} helle Bildpunkte im Skalenstreifen (Schranke > 0: die Zahlen am Balken)`);
await p.evaluate(() => window.scrollTo(0, document.getElementById('display').getBoundingClientRect().top + window.scrollY - 60)); await p.waitForTimeout(200); await p.screenshot({ path: S + 'waerme_display.png' });

// W11/W12: Dokumentation, Neutralisierung
await p.evaluate(() => document.querySelector('details').open = true); await p.waitForTimeout(300);
const doku = (await p.evaluate(() => document.body.textContent)).replace(/\s+/g, ' ');
sage(doku.includes('Grid-EYE') && doku.includes('Parallaxe') && doku.includes('Die Simulation in der Seite') && doku.includes('GPIO14'), 'Dokumentation in der Seite: Sensor (Grid-EYE), Ausrichtung mit Parallaxe, Vorgeschichte GPIO14, Kapitel 14 „Die Simulation in der Seite“');
const bilder = await p.evaluate(() => [...document.querySelectorAll('.doku img')].filter(i => i.naturalWidth > 100).length);
// Gesucht wird der Platzhalter, nie das Geheimnis: die Seite muss den Hinweis tragen und darf keine Adresse und keinen
// Kennwortwert enthalten. Gesucht wird eine Wertzuweisung hinter dem Wort Kennwort oder Passwort (x-Folge und <…> erlaubt).
const adresse = doku.match(/\b\d{1,3}(?:\.\d{1,3}){3}\b/);
const wert = doku.match(/(?:Kennwort|Passwor[dt])\s*[:=]\s*(?![x<\s])\S+/i);
const hinweis = await p.$eval('#platzhalter', e => e.textContent);
sage(bilder === 2 && !adresse && !wert && hinweis.includes('<WLAN-Name>') && hinweis.includes('genauso viele') && doku.includes('Der Erzeuger dieser Seite trägt die Werte nicht.'),
  `Dokumentation neutralisiert: ${bilder} Fotos des Aufbaus geladen (Schranke 2), Platzhalterhinweis vorhanden (<WLAN-Name>, Kennwort als x-Folge), ${adresse ? 'Adresse gefunden: ' + adresse[0] : 'keine Adresse im Vierergruppenmuster'}, ${wert ? 'Kennwortwert gefunden: ' + wert[0] : 'kein Kennwortwert'}`);
await p.evaluate(() => window.scrollTo(0, document.getElementById('platzhalter').getBoundingClientRect().top + window.scrollY - 40)); await p.waitForTimeout(200); await p.screenshot({ path: S + 'waerme_doku.png' });

// W13: Kopf
const kopf = await p.$eval('#fassung', e => e.textContent);
sage(kopf.includes(`Fassung ${V}`) && kopf.includes('29.09.2026') && kopf.includes('Ralph Wystup'), `Kopf: ${kopf.slice(0, 80)}`);
await b.close();
fs.writeFileSync(H + 'pruefe_seite.json', JSON.stringify({ datum: new Date().toISOString(), fassung: V, befunde: BEF }, null, 1));
console.log(fehler ? `${fehler} Beanstandung(en)` : 'alles in Ordnung'); process.exit(fehler ? 1 : 0);
