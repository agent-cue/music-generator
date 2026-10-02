"""Fotografiert die laufende Oberfläche für die Installationsanleitung.

Startet ein unsichtbares Chrome mit leerem, temporärem Profil (dein normales Chrome bleibt unberührt),
macht zwei Aufnahmen und liest dabei die Positionen der Elemente aus:

    form.png   Kopfzeile + Formular (Seite 5)
    row.png    eine Songzeile der Bibliothek (Seite 6)
    marks.json Positionen für die nummerierten Markierungen im PDF

Aufruf (App muss laufen):
    uv run --with websockets python docs/anleitung/capture.py [http://127.0.0.1:8765/]
"""
import base64
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from websockets.sync.client import connect

HERE = Path(__file__).parent
URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765/"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
WIDTH, HEIGHT, SCALE = 900, 1700, 2   # CSS-Pixel; Bilder entstehen in doppelter Auflösung

# Wird auf der Seite ausgeführt: bereitet sie vor und liest Rechtecke (CSS-Pixel, Seitenkoordinaten) aus.
PAGE_JS = r"""
(() => {
  document.querySelector('#lyricsBox').open = false;
  document.querySelectorAll('details').forEach(d => d.open = false);
  document.activeElement && document.activeElement.blur();
  window.scrollTo(0, 0);
  const R = (el) => { const r = el.getBoundingClientRect(); return {x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height}; };
  const T = (el) => { const g = document.createRange(); g.selectNodeContents(el); return R({getBoundingClientRect: () => g.getBoundingClientRect()}); };
  const lbl = (t) => [...document.querySelectorAll('.lbl')].find(e => e.textContent.trim().toLowerCase().startsWith(t));
  const song = [...document.querySelectorAll('.song')].find(s => s.querySelector('.download'));
  const q = (sel) => document.querySelector(sel);
  const card = R(q('.card'));
  return JSON.stringify({
    card,
    logo: R(q('.logo-wrap')), titleDice: R(q('#titleDice')), promptDice: R(q('#diceBtn')),
    stil: T(lbl('stil')), laenge: T(lbl('länge')), bpm: T(lbl('bpm')),
    lyrics: T(q('#lyricsBox summary > span')), erweitert: T(q('details:not(#lyricsBox) summary')),
    gen: R(q('#genBtn')), gear: R(q('#btnSettings')),
    row: song ? R(song) : null,
    rowParts: song ? ['.round', '[data-a=fav]', '.download', '[data-a=more]', '[data-a=reuse]', '[data-a=del]'].map(s => R(song.querySelector(s))) : null,
  });
})()
"""


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Cdp:
    def __init__(self, ws):
        self.ws = ws
        self.n = 0

    def call(self, method, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def eval(self, js):
        r = self.call("Runtime.evaluate", expression=js, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")

    def shot(self, path, x, y, w, h):
        r = self.call("Page.captureScreenshot", format="png",
                      clip={"x": x, "y": y, "width": w, "height": h, "scale": 1})
        Path(path).write_bytes(base64.b64decode(r["data"]))


def main():
    profile = tempfile.mkdtemp(prefix="mg-capture-")
    port = free_port()
    proc = subprocess.Popen(
        [CHROME, "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={profile}",
         "--no-first-run", "--hide-scrollbars", "--disable-gpu", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        targets = None
        for _ in range(60):
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1))
                if any(t.get("type") == "page" for t in targets):
                    break
            except OSError:
                pass
            time.sleep(0.5)
        else:
            sys.exit("Chrome ließ sich nicht starten.")
        page = next(t for t in targets if t.get("type") == "page")
        with connect(page["webSocketDebuggerUrl"], max_size=None) as ws:
            capture(Cdp(ws))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)


def capture(cdp):
    if True:
        cdp.call("Page.enable")
        cdp.call("Emulation.setDeviceMetricsOverride", width=WIDTH, height=HEIGHT, deviceScaleFactor=SCALE, mobile=False)
        cdp.call("Page.navigate", url=URL)
        for _ in range(60):
            if cdp.eval("document.readyState === 'complete' && !!document.querySelector('.song .download')"):
                break
            time.sleep(0.5)
        else:
            sys.exit("Die App antwortet nicht oder hat noch keinen fertigen Song. Läuft sie unter " + URL + " ?")
        time.sleep(1.0)
        d = json.loads(cdp.eval(PAGE_JS))
        time.sleep(0.3)

        card = d["card"]
        fh = card["y"] + card["h"] + 8         # bis knapp unter das Formular
        cdp.shot(HERE / "form.png", 0, 0, WIDTH, fh)
        row = d["row"]
        cdp.shot(HERE / "row.png", row["x"], row["y"], row["w"], row["h"])

        mid = lambda r: (r["x"] + r["w"] / 2, r["y"] + r["h"] / 2)
        # Nummern neben die Elemente setzen, nicht darauf (CSS-Pixel im Bild)
        marks = [
            (mid(d["logo"])[0], d["logo"]["y"] + d["logo"]["h"] + 4),
            (d["titleDice"]["x"] - 30, mid(d["titleDice"])[1]),
            (d["promptDice"]["x"] - 30, mid(d["promptDice"])[1]),
            (d["stil"]["x"] + d["stil"]["w"] + 30, mid(d["stil"])[1]),
            (d["laenge"]["x"] + d["laenge"]["w"] + 30, mid(d["laenge"])[1]),
            (d["bpm"]["x"] + d["bpm"]["w"] + 30, mid(d["bpm"])[1]),
            (d["lyrics"]["x"] + d["lyrics"]["w"] + 30, mid(d["lyrics"])[1]),
            (d["erweitert"]["x"] + d["erweitert"]["w"] + 30, mid(d["erweitert"])[1]),
            (d["gen"]["x"] + d["gen"]["w"] - 22, d["gen"]["y"] - 30),
            (d["gear"]["x"] - 30, mid(d["gear"])[1]),
        ]
        out = {
            "form": {"w": WIDTH, "h": fh, "marks": [[round(x, 1), round(y, 1)] for x, y in marks]},
            "row": {"w": row["w"], "h": row["h"],
                    "xs": [round(mid(p)[0] - row["x"], 1) for p in d["rowParts"]]},
        }
        (HERE / "marks.json").write_text(json.dumps(out, indent=1))
        print("ok:", out["form"]["w"], "x", round(out["form"]["h"]), "· Zeile", round(row["w"]), "x", round(row["h"]))


main()
