# -*- coding: utf-8 -*-
"""
thermo_cam_dashboard.py
Thermo-Fusion-Dashboard -- komplett ueber HTTP, ohne Modbus:

  * KAMERABILD: MJPEG-Livestream direkt von der ESP32-CAM (Port 81);
    der Browser laedt ihn selbst. Schnell und fluessig.
  * WAERMEBILD: 64 Temperaturen des AMG8833 vom Display-Board als
    HTTP/JSON (main.py dort, Endpunkt /thermo), 2x je Sekunde; wird im
    Browser weich interpoliert TEILTRANSPARENT ueber den Stream gelegt
    (Eisenpalette).
  * AUSRICHTUNG: Regler fuer Position/Groesse/Transparenz/Spiegelung;
    "Speichern" legt die Einstellung dauerhaft auf dem Display-Board ab
    (ausrichtung.json).
  * Temperaturskala (Max oben, Min unten) und Datum/Uhrzeit wie beim
    Display-Geraet.

Reines Python ohne Zusatzpakete.  Aufruf:  python thermo_cam_dashboard.py
Browser:  http://localhost:8084
"""
import json
import socket
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

# ------------- Einstellungen -------------
ESP32CAM_IP      = "<IP-der-Kamera>"   # ESP32-CAM: liefert den Stream
DISPLAY_IP       = "<IP-des-Display-Boards>"   # Display-Board: Thermodaten (IP aus Thonny!)
STREAM_PORT      = 81                  # MJPEG-Stream der ESP32-CAM
THERMO_INTERVALL = 0.5                 # s zwischen zwei Thermo-Abfragen
WEB_PORT         = 8084
# -----------------------------------------

datenschloss = threading.Lock()

zustand = {
    "verbunden": False, "meldung": "starte ...",
    "thermo_ok": 1,
    "thermo": [0.0] * 64,
    "einst": {"ox": 0, "oy": 0, "sk": 100, "al": 45, "sp": 0},
    "stream": "http://%s:%d/stream" % (ESP32CAM_IP, STREAM_PORT),
}


def display_abfrage(pfad):
    """HTTP-GET zum Display-Board, JSON-Antwort zurueckgeben."""
    with urllib.request.urlopen("http://%s%s" % (DISPLAY_IP, pfad),
                                timeout=3.0) as antwort:
        return json.loads(antwort.read().decode())


def abfrageschleife():
    erste = True
    while True:
        try:
            paket = display_abfrage("/thermo")
            with datenschloss:
                zustand["thermo"] = paket["t"]
                if erste:                      # gespeicherte Ausrichtung holen
                    zustand["einst"] = paket["einst"]
                    erste = False
                zustand["verbunden"] = True
                zustand["meldung"] = "OK"
        except Exception as e:
            with datenschloss:
                zustand["verbunden"] = False
                zustand["meldung"] = str(e) or e.__class__.__name__
            time.sleep(2.0)
        time.sleep(THERMO_INTERVALL)


# ---------------- Web-Oberflaeche ----------------

SEITE = r"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Thermo-Fusion Dashboard</title>
<style>
:root{--flaeche:#fcfcfb;--seite:#f9f9f7;--tinte:#0b0b0b;--tinte2:#52514e;
 --rand:rgba(11,11,11,.10);--serie:#2a78d6;--gut:#0ca30c;--kritisch:#d03b3b;}
@media (prefers-color-scheme:dark){:root{--flaeche:#1a1a19;--seite:#0d0d0d;
 --tinte:#fff;--tinte2:#c3c2b7;--rand:rgba(255,255,255,.10);--serie:#3987e5;}}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:var(--seite);
 color:var(--tinte);padding:16px}
h1{font-size:1.15rem;font-weight:600}
h2{font-size:.95rem;font-weight:600;margin-bottom:8px}
.kopf{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:14px}
.status{display:flex;align-items:center;gap:6px;font-size:.85rem;color:var(--tinte2)}
.punkt{width:9px;height:9px;border-radius:50%;background:var(--kritisch)}
.punkt.an{background:var(--gut)}
.karte{background:var(--flaeche);border:1px solid var(--rand);border-radius:10px;
 padding:14px 16px;margin-bottom:14px}
.zeilen{display:flex;gap:14px;flex-wrap:wrap;align-items:flex-start}
.fehlerband{color:var(--kritisch);font-size:.85rem;margin-bottom:10px;display:none}
#buehne{position:relative;width:640px;height:480px;overflow:hidden;
 background:#000;border-radius:6px;flex:none}
#stream{position:absolute;left:0;top:0;width:640px;height:480px}
#thermo{position:absolute;image-rendering:auto;pointer-events:none}
#uhr{font-size:.9rem;color:var(--tinte2);margin-top:6px;
 font-variant-numeric:tabular-nums}
#skala{width:40px;height:480px;flex:none;display:flex;flex-direction:column;
 align-items:center}
#skala canvas{width:16px;height:432px;border-radius:3px}
#skala .wert{font-size:.8rem;font-variant-numeric:tabular-nums;height:24px;
 display:flex;align-items:center}
.regler{min-width:280px;flex:1}
.regler label{display:block;font-size:.82rem;color:var(--tinte2);margin-top:10px}
.regler input[type=range]{width:100%}
.regler .wert{color:var(--tinte);font-variant-numeric:tabular-nums}
button{font:inherit;border:1px solid var(--rand);border-radius:7px;padding:8px 16px;
 background:var(--flaeche);color:var(--tinte);cursor:pointer;margin-top:14px}
button:hover{border-color:var(--serie)}
#spstatus{font-size:.8rem;color:var(--gut);margin-left:8px}
.cb{margin-top:10px;font-size:.85rem}
</style></head><body>
<div class="kopf"><h1>Thermo-Fusion: Kamera + W&auml;rmebild</h1>
 <span class="status"><span id="lampe" class="punkt"></span><span id="statustext">verbinde &hellip;</span></span></div>
<div id="fehlerband" class="fehlerband"></div>

<div class="zeilen">
 <div class="karte" style="flex:none">
  <div class="zeilen">
   <div id="buehne">
    <img id="stream" alt="Kamerastream">
    <canvas id="thermo" width="8" height="8"></canvas>
   </div>
   <div id="skala">
    <div class="wert" id="tmax">&ndash;</div>
    <canvas id="balken" width="16" height="432"></canvas>
    <div class="wert" id="tmin">&ndash;</div>
   </div>
  </div>
  <div id="uhr">&ndash;</div>
 </div>

 <div class="karte regler"><h2>Ausrichtung W&auml;rmebild</h2>
  <label>Position X: <span class="wert" id="oxw">0</span> px
   <input type="range" id="ox" min="-250" max="250" value="0"></label>
  <label>Position Y: <span class="wert" id="oyw">0</span> px
   <input type="range" id="oy" min="-250" max="250" value="0"></label>
  <label>Gr&ouml;&szlig;e: <span class="wert" id="skw">100</span> %
   <input type="range" id="sk" min="25" max="400" value="100"></label>
  <label>Transparenz: <span class="wert" id="alw">45</span> % sichtbar
   <input type="range" id="al" min="0" max="100" value="45"></label>
  <div class="cb"><label><input type="checkbox" id="sph"> horizontal spiegeln</label></div>
  <div class="cb"><label><input type="checkbox" id="spv"> vertikal spiegeln</label></div>
  <button onclick="speichern()">Ausrichtung speichern</button><span id="spstatus"></span>
  <p style="font-size:.75rem;color:var(--tinte2);margin-top:12px">
   Vorgehen: warmes Objekt (Hand, Tasse) ins Bild halten und mit den
   Reglern zur Deckung bringen. "Speichern" legt die Ausrichtung dauerhaft
   auf dem Display-Board ab (ausrichtung.json). Kamera und W&auml;rmesensor
   dicht beieinander montieren, gleiche Blickrichtung.</p>
 </div>
</div>

<script>
const W=640, H=480;
const STUETZEN=[[0,0,0],[32,0,96],[160,0,160],[255,64,0],[255,200,0],[255,255,255]];
function farbe(f){
 const seg=STUETZEN.length-1, p=f*seg, s=Math.min(Math.floor(p),seg-1), t=p-s;
 return [0,1,2].map(i=>Math.round(STUETZEN[s][i]+(STUETZEN[s+1][i]-STUETZEN[s][i])*t));
}
let daten=null, einst={ox:0,oy:0,sk:100,al:45,sp:0}, uebernommen=false;
let sMin=20, sMax=30;
const MIN_SPANNE=4, GLAETT=0.3;

const tctx=document.getElementById('thermo').getContext('2d');

function malen(){
 if(!daten)return;
 const mn=Math.min(...daten.thermo), mx=Math.max(...daten.thermo);
 sMin+=(mn-sMin)*GLAETT; sMax+=(mx-sMax)*GLAETT;
 let lo=sMin, hi=sMax;
 if(hi-lo<MIN_SPANNE){const m=(hi+lo)/2; lo=m-MIN_SPANNE/2; hi=m+MIN_SPANNE/2;}
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
}

function balken_zeichnen(){
 const c=document.getElementById('balken'), x=c.getContext('2d');
 for(let y=0;y<c.height;y++){
  const [r,g,b]=farbe(1-y/(c.height-1));
  x.fillStyle='rgb('+r+','+g+','+b+')'; x.fillRect(0,y,c.width,1);
 }
}
balken_zeichnen();

async function hole(){
 try{daten=await(await fetch('/daten')).json();}catch(e){setStatus(false,'Server weg');return;}
 setStatus(daten.verbunden, daten.verbunden?'verbunden':daten.meldung);
 if(!uebernommen && daten.verbunden){
  einst=daten.einst; uebernommen=true;
  ox.value=einst.ox; oy.value=einst.oy; sk.value=einst.sk; al.value=einst.al;
  sph.checked=!!(einst.sp&1); spv.checked=!!(einst.sp&2);
  zeige_werte();
 }
 const s=document.getElementById('stream');
 if(!s.src) s.src=daten.stream;
 malen();
}
function setStatus(an,text){lampe.className='punkt'+(an?' an':'');
 statustext.textContent=text;
 fehlerband.style.display=an?'none':'block';
 fehlerband.textContent=an?'':'Keine Verbindung zum Display-Board: '+text;}

function zeige_werte(){oxw.textContent=einst.ox; oyw.textContent=einst.oy;
 skw.textContent=einst.sk; alw.textContent=einst.al;}

let sende_timer=null;
function geaendert(){
 einst={ox:Number(ox.value), oy:Number(oy.value), sk:Number(sk.value),
        al:Number(al.value), sp:(sph.checked?1:0)|(spv.checked?2:0)};
 zeige_werte(); malen();
 clearTimeout(sende_timer);
 sende_timer=setTimeout(()=>fetch('/einstellung?ox='+einst.ox+'&oy='+einst.oy+
   '&sk='+einst.sk+'&al='+einst.al+'&sp='+einst.sp), 200);
}
for(const id of ['ox','oy','sk','al','sph','spv'])
 document.getElementById(id).addEventListener('input', geaendert);

async function speichern(){
 const r=await fetch('/speichern');
 spstatus.textContent=r.ok?'gespeichert!':'Fehler';
 setTimeout(()=>spstatus.textContent='',3000);
}

function uhr(){
 const j=new Date();
 const z=n=>String(n).padStart(2,'0');
 document.getElementById('uhr').textContent=
  z(j.getDate())+'.'+z(j.getMonth()+1)+'.'+j.getFullYear()+'  '+
  z(j.getHours())+':'+z(j.getMinutes())+':'+z(j.getSeconds());
}
setInterval(uhr,1000); uhr();
hole(); setInterval(hole,500);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def antwort(self, inhalt, typ="application/json"):
        self.send_response(200)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(inhalt)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(inhalt)

    def do_GET(self):
        url = urlparse(self.path)
        try:
            if url.path == "/":
                self.antwort(SEITE.encode("utf-8"), "text/html; charset=utf-8")
            elif url.path == "/daten":
                with datenschloss:
                    paket = dict(zustand)
                self.antwort(json.dumps(paket).encode("utf-8"))
            elif url.path == "/einstellung":
                # 1:1 ans Display-Board weiterreichen
                display_abfrage("/einstellung?" + (url.query or ""))
                self.antwort(b'{"ok":true}')
            elif url.path == "/speichern":
                display_abfrage("/speichern")
                self.antwort(b'{"ok":true}')
            else:
                self.send_error(404)
        except Exception as e:
            self.antwort(json.dumps({"ok": False, "fehler": str(e)}).encode("utf-8"))

    def log_message(self, *args):
        pass


def eigene_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 1)); return s.getsockname()[0]
    except OSError:
        return "localhost"
    finally:
        s.close()


def main():
    threading.Thread(target=abfrageschleife, daemon=True).start()
    server = ThreadingHTTPServer(("", WEB_PORT), Handler)
    print("Thermo-Fusion-Dashboard:  http://localhost:%d" % WEB_PORT)
    print("  im Netz:                http://%s:%d" % (eigene_ip(), WEB_PORT))
    print("  Kamera-Stream:          http://%s:%d/stream (ESP32-CAM)" %
          (ESP32CAM_IP, STREAM_PORT))
    print("  Thermodaten (HTTP):     http://%s/thermo (Display-Board), alle %.1f s" %
          (DISPLAY_IP, THERMO_INTERVALL))
    print("Beenden mit Strg+C.")
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nBeendet.")
