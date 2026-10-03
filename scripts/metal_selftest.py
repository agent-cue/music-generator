"""Prüft, ob das Sprachmodell unter Metal brauchbar rechnet.

Beide Phasen werden getestet: Phase 1 plant Tempo, Tonart und Takt (deshalb geben wir sie
nicht vor), Phase 2 erzeugt die Audio-Codes. Auf dem Apple M4 scheitert mit acestep.cpp b7ba6d9
das 1.7B-Modell unter Metal an beidem (Phase 1 läuft ins Token-Limit, danach 0 Codes),
das 0.6B-Modell dagegen funktioniert.

Aufruf: python metal_selftest.py <port> [lm_datei]
Exit 0 = Metal ok (ein Server reicht), Exit 1 = Sprachmodell muss auf die CPU.
"""
import sys
import time

import httpx

port = int(sys.argv[1])
lm_file = sys.argv[2] if len(sys.argv) > 2 else ""
base = f"http://127.0.0.1:{port}"
DURATION = 10  # Sekunden -> erwartet ~50 Codes (5 pro Sekunde)
req = {
    "caption": "calm ambient pad, soft piano",
    "lyrics": "[Instrumental]",
    "duration": DURATION,
    "vocal_language": "unknown",
    "seed": 42,
}
if lm_file:
    req["lm_model"] = lm_file

try:
    with httpx.Client(timeout=30) as c:
        job = c.post(f"{base}/lm", json=req).json()["id"]
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            status = str(c.get(f"{base}/job", params={"id": job}).json().get("status", "")).lower()
            if status == "done":
                break
            if any(w in status for w in ("err", "fail", "cancel")):
                print(f"Selbsttest: Job fehlgeschlagen ({status})")
                sys.exit(1)
            time.sleep(1)
        else:
            print("Selbsttest: Zeitüberschreitung")
            sys.exit(1)
        result = c.get(f"{base}/job", params={"id": job, "result": 1}).json()
except Exception as e:  # noqa: BLE001
    print(f"Selbsttest: {e}")
    sys.exit(1)

data = result[0] if isinstance(result, list) else result
codes = [x for x in str(data.get("audio_codes", "")).split(",") if x.strip()]
expected = DURATION * 5
unique_ratio = len(set(codes)) / len(codes) if codes else 0
try:
    bpm = float(data.get("bpm") or 0)
except (TypeError, ValueError):
    bpm = 0
# Phase 1: nur prüfen, dass überhaupt geplant wurde. Das 0.6B-Modell wählt auch mal 37 BPM, das ist kein Metal-Fehler.
planned = bpm > 0 and bool(data.get("keyscale"))
coded = 0.6 * expected <= len(codes) <= 1.4 * expected and unique_ratio > 0.3   # Phase 2
ok = planned and coded
print(f"Selbsttest: Planung {'ok' if planned else 'fehlerhaft'} (BPM {data.get('bpm')}, {data.get('keyscale') or 'keine Tonart'}), "
      f"{len(codes)} Codes (erwartet ~{expected}), Vielfalt {unique_ratio:.2f} -> {'ok' if ok else 'unbrauchbar'}")
sys.exit(0 if ok else 1)
