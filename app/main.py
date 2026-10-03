"""FastAPI-Backend: Job-Queue, Bibliothek, Einstellungen."""
import asyncio
import json
import random
import re
import subprocess
import sys
import tempfile
import uuid
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from . import db, updater
from .engines import EngineError, make_engine

STATIC = db.ROOT / "static"
_wakeup = asyncio.Event()
_running: dict = {}   # laufender Auftrag: {"sid", "task", "engine"} – zum Abbrechen


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- Worker

async def worker():
    """Arbeitet die Queue strikt nacheinander ab (eine GPU, ein Job)."""
    while True:
        job = db.one("SELECT * FROM songs WHERE status='queued' ORDER BY created_at, rowid LIMIT 1")
        if not job:
            _wakeup.clear()
            await _wakeup.wait()
            continue
        sid = job["id"]
        db.execute("UPDATE songs SET status='running', message='0:00' WHERE id=?", (sid,))
        engine = make_engine(db.get_settings())

        async def progress(msg: str):
            db.execute("UPDATE songs SET message=? WHERE id=? AND status='running'", (msg, sid))

        try:
            params = json.loads(job["params"])
            gen = asyncio.create_task(engine.generate(params, progress))
            _running.update(sid=sid, task=gen, engine=engine)
            try:
                audio, ext, meta = await gen
            except asyncio.CancelledError:
                if not gen.cancelled() or asyncio.current_task().cancelling():
                    raise                   # die App selbst wird beendet
                await engine.cancel()       # vom Nutzer abgebrochen (Status steht schon auf "cancelled")
                continue
            finally:
                _running.clear()
            fname = f"{sid}.{ext}"
            (db.SONGS_DIR / fname).write_bytes(audio)
            if db.one("SELECT status FROM songs WHERE id=?", (sid,))["status"] == "running":
                db.execute(
                    "UPDATE songs SET status='done', message=NULL, file=?, engine=?, result_meta=?, finished_at=? WHERE id=?",
                    (fname, engine.name, json.dumps(meta), now(), sid),
                )
        except (EngineError, Exception) as e:  # noqa: BLE001 – Fehler landen sichtbar im UI
            text = str(e) or e.__class__.__name__
            if "ConnectError" in repr(e) or "connect" in text.lower():
                text = f"Modellserver nicht erreichbar ({db.get_settings()['server_url']}). Läuft ace-server?"
            db.execute("UPDATE songs SET status='error', message=?, finished_at=? WHERE id=?", (text, now(), sid))


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    for old in db.DATA.glob("mg-*.zip"):   # Reste abgebrochener Downloads
        old.unlink(missing_ok=True)
    if sys.platform == "darwin":   # Symbole der Start-Dateien erneuern (Git/ZIP setzen sie zurück)
        subprocess.Popen(["bash", str(Path(__file__).resolve().parent.parent / "scripts" / "symbole.sh")],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    task = asyncio.create_task(worker())
    _wakeup.set()
    yield
    task.cancel()


app = FastAPI(title="Music Generator", lifespan=lifespan)
app.include_router(updater.router)


@app.middleware("http")
async def no_cache(request, call_next):
    """Oberfläche nie aus dem Browser-Cache laden, sonst sieht man alte Stände."""
    resp = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


# ---------------------------------------------------------------- Modelle

class GenerateRequest(BaseModel):
    prompt: str = ""               # Idee / Beschreibung für den Song
    style: str = ""                # Stilrichtung (Genre-Tags)
    caption: str = ""              # nur für ältere Songs: fertiger Text; sonst aus style + prompt gebaut
    lyrics: str = ""
    instrumental: bool = True
    keep_caption: bool = True      # True = Modell schreibt die Beschreibung nicht um
    title: str = ""
    duration: float = 0            # 0 = Modell entscheidet
    bpm: int = 0
    keyscale: str = ""
    timesignature: str = ""
    vocal_language: str = ""
    seed: int = -1                 # -1 = zufällig (wird trotzdem gespeichert)
    variants: int = Field(1, ge=1, le=50)
    inference_steps: int = 0
    lm_temperature: float | None = None
    group_id: str | None = None    # für "weitere Variante" einer bestehenden Gruppe
    folder_id: str | None = None   # Ordner der Bibliothek, in dem die neuen Songs landen


class SongPatch(BaseModel):
    favorite: bool | None = None
    title: str | None = None
    folder_id: str | None = None   # None/"" = unsortiert (nur ausgewertet, wenn mitgeschickt)


class FolderIn(BaseModel):
    name: str


def letters() -> dict:
    """Versionen desselben Prompts heißen in Entstehungsreihenfolge A, B, C … (über alle Ordner hinweg)."""
    groups: dict = {}
    for r in db.query("SELECT id, group_id FROM songs ORDER BY created_at, rowid"):
        groups.setdefault(r["group_id"], []).append(r["id"])
    return {sid: chr(65 + i) for ids in groups.values() if len(ids) > 1 for i, sid in enumerate(ids) if i < 26}


def folder_where(folder: str) -> tuple[str, list]:
    """Filter der Bibliothek: "" = alle, "none" = unsortiert, sonst Ordner-ID."""
    if folder == "none":
        return " AND folder_id IS NULL", []
    if folder:
        return " AND folder_id=?", [folder]
    return "", []


def song_out(r: dict, letter: dict | None = None) -> dict:
    r["letter"] = (letter or {}).get(r["id"], "")
    r["params"] = json.loads(r["params"])
    r["result_meta"] = json.loads(r["result_meta"]) if r["result_meta"] else None
    r["favorite"] = bool(r["favorite"])
    r["url"] = f"/api/songs/{r['id']}/audio" if r["file"] else None
    return r


# ---------------------------------------------------------------- API

@app.post("/api/generate")
async def generate(req: GenerateRequest):
    group = req.group_id or uuid.uuid4().hex[:12]
    lyrics = "[Instrumental]" if req.instrumental else req.lyrics.strip()
    parts = [p.strip().strip(",") for p in (req.style, req.prompt) if p.strip()]
    caption = ", ".join(parts) if parts else req.caption.strip()
    if not caption:
        raise HTTPException(422, "Prompt oder Stil fehlt")
    base = req.model_dump(exclude={"variants", "group_id", "folder_id", "instrumental", "title", "keep_caption"})
    base["caption"] = caption
    base["use_cot_caption"] = not req.keep_caption
    base["lyrics"] = lyrics
    folder = req.folder_id if req.folder_id and db.one("SELECT id FROM folders WHERE id=?", (req.folder_id,)) else None
    ids = []
    for i in range(req.variants):
        # Erste Variante nimmt den festen Seed, weitere zählen hoch -> alles reproduzierbar
        seed = random.randint(0, 2**31 - 1) if req.seed < 0 else req.seed + i
        params = {**base, "seed": seed}
        sid = uuid.uuid4().hex[:12]
        db.execute(
            "INSERT INTO songs(id, group_id, created_at, status, title, caption, lyrics, seed, params, folder_id) "
            "VALUES(?,?,?,?,?,?,?,?,?,?)",
            (sid, group, now(), "queued", req.title.strip() or None, caption, lyrics, seed, json.dumps(params), folder),
        )
        ids.append(sid)
    _wakeup.set()
    return {"group_id": group, "ids": ids}


@app.get("/api/songs")
def list_songs(q: str = "", favorites: bool = False, group: str = "", folder: str = ""):
    sql, args = "SELECT * FROM songs WHERE 1=1", []
    if q:
        sql += " AND (caption LIKE ? OR lyrics LIKE ? OR title LIKE ?)"
        args += [f"%{q}%"] * 3
    if favorites:
        sql += " AND favorite=1"
    if group:
        sql += " AND group_id=?"
        args.append(group)
    fw, fa = folder_where(folder)
    sql += fw + " ORDER BY created_at DESC, rowid DESC LIMIT 500"
    lt = letters()
    return [song_out(r, lt) for r in db.query(sql, tuple(args + fa))]


@app.get("/api/songs/{sid}")
def get_song(sid: str):
    r = db.one("SELECT * FROM songs WHERE id=?", (sid,))
    if not r:
        raise HTTPException(404)
    return song_out(r)


@app.patch("/api/songs/{sid}")
def patch_song(sid: str, p: SongPatch):
    if p.favorite is not None:
        db.execute("UPDATE songs SET favorite=? WHERE id=?", (int(p.favorite), sid))
    if p.title is not None:
        db.execute("UPDATE songs SET title=? WHERE id=?", (p.title.strip() or None, sid))
    if "folder_id" in p.model_fields_set:
        db.execute("UPDATE songs SET folder_id=? WHERE id=?", (p.folder_id or None, sid))
    return get_song(sid)


@app.post("/api/songs/{sid}/retry")
async def retry_song(sid: str):
    db.execute("UPDATE songs SET status='queued', message=NULL WHERE id=? AND status IN ('error','cancelled')", (sid,))
    _wakeup.set()
    return get_song(sid)


@app.delete("/api/songs/{sid}")
async def delete_song(sid: str):
    r = db.one("SELECT * FROM songs WHERE id=?", (sid,))
    if not r:
        raise HTTPException(404)
    if r["status"] == "queued":
        db.execute("UPDATE songs SET status='cancelled' WHERE id=?", (sid,))
        return {"cancelled": True}
    if r["status"] == "running":
        db.execute("UPDATE songs SET status='cancelled', message=NULL, finished_at=? WHERE id=?", (now(), sid))
        if _running.get("sid") == sid:
            _running["task"].cancel()
        return {"cancelled": True}
    if r["file"]:
        (db.SONGS_DIR / r["file"]).unlink(missing_ok=True)
    db.execute("DELETE FROM songs WHERE id=?", (sid,))
    return {"deleted": True}


@app.get("/api/songs/{sid}/audio")
def song_audio(sid: str, download: bool = False):
    r = db.one("SELECT * FROM songs WHERE id=?", (sid,))
    if not r or not r["file"]:
        raise HTTPException(404)
    path = db.SONGS_DIR / r["file"]
    name = None
    if download:
        base = r["title"] or r["caption"][:40]
        base = re.sub(r"[^\w\- ]+", "", base).strip().replace(" ", "_") or "song"
        name = f"{base}_{r['seed']}{path.suffix}"
    return FileResponse(path, filename=name)


# ---------------------------------------------------------------- Ordner

@app.get("/api/folders")
def list_folders():
    counts = {r["folder_id"]: r["n"] for r in db.query("SELECT folder_id, COUNT(*) AS n FROM songs GROUP BY folder_id")}
    folders = db.query("SELECT id, name FROM folders ORDER BY name COLLATE NOCASE")
    known = {f["id"] for f in folders}
    for f in folders:
        f["count"] = counts.get(f["id"], 0)
    # Songs, deren Ordner es nicht mehr gibt, zählen als unsortiert
    return {"folders": folders, "all": sum(counts.values()), "none": sum(n for k, n in counts.items() if k not in known)}


@app.post("/api/folders")
def create_folder(f: FolderIn):
    name = f.name.strip()[:60]
    if not name:
        raise HTTPException(422, "Name fehlt")
    fid = uuid.uuid4().hex[:12]
    db.execute("INSERT INTO folders(id, name, created_at) VALUES(?,?,?)", (fid, name, now()))
    return {"id": fid, "name": name}


@app.patch("/api/folders/{fid}")
def rename_folder(fid: str, f: FolderIn):
    name = f.name.strip()[:60]
    if not name:
        raise HTTPException(422, "Name fehlt")
    db.execute("UPDATE folders SET name=? WHERE id=?", (name, fid))
    return {"id": fid, "name": name}


@app.delete("/api/folders/{fid}")
def delete_folder(fid: str):
    """Löscht nur den Ordner; seine Songs werden wieder unsortiert."""
    db.execute("UPDATE songs SET folder_id=NULL WHERE folder_id=?", (fid,))
    db.execute("DELETE FROM folders WHERE id=?", (fid,))
    return {"deleted": True}


@app.get("/api/download")
def download_zip(folder: str = ""):
    """Alle fertigen Songs der Ansicht (alle / unsortiert / ein Ordner) als ZIP mit lesbaren Dateinamen."""
    fw, fa = folder_where(folder)
    rows = db.query("SELECT * FROM songs WHERE status='done' AND file IS NOT NULL" + fw + " ORDER BY created_at, rowid", tuple(fa))
    rows = [r for r in rows if (db.SONGS_DIR / r["file"]).is_file()]
    if not rows:
        raise HTTPException(404, "Keine fertigen Songs in dieser Ansicht.")
    clean = lambda s: re.sub(r"[^\w\- ]+", "", s).strip()   # noqa: E731
    f = db.one("SELECT name FROM folders WHERE id=?", (folder,)) if folder not in ("", "none") else None
    zip_name = clean(f["name"] if f else "Music Generator") or "Music Generator"
    lt, used = letters(), set()
    tmp = tempfile.NamedTemporaryFile(prefix="mg-", suffix=".zip", dir=db.DATA, delete=False)
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z:   # WAV lässt sich kaum packen -> nur bündeln
        for r in rows:
            path = db.SONGS_DIR / r["file"]
            base = " ".join(x for x in (clean(r["title"] or r["caption"][:40]) or "Song", lt.get(r["id"], "")) if x)
            name = f"{base}{path.suffix}"
            if name.lower() in used:
                name = f"{base} {r['seed']}{path.suffix}"
            used.add(name.lower())
            z.write(path, f"{zip_name}/{name}")
    tmp.close()
    return FileResponse(tmp.name, filename=f"{zip_name}.zip", media_type="application/zip",
                        background=BackgroundTask(Path(tmp.name).unlink, missing_ok=True))


@app.get("/api/queue")
def queue():
    rows = db.query("SELECT id, status, message, caption FROM songs WHERE status IN ('queued','running') ORDER BY created_at, rowid")
    files = [f.stat().st_size for f in db.SONGS_DIR.iterdir() if f.is_file()]
    return {"running": [r for r in rows if r["status"] == "running"], "queued": len([r for r in rows if r["status"] == "queued"]),
            "library": {"count": len(files), "bytes": sum(files)}}


@app.get("/api/settings")
def get_settings():
    return db.get_settings()


@app.put("/api/settings")
def put_settings(values: dict):
    return db.save_settings(values)


@app.post("/api/analyze")
async def analyze(audio: UploadFile):
    """Song hochladen -> Modell liefert Stil, Tempo, Tonart, Lyrics als Vorschlag fürs Formular."""
    if not (audio.content_type or "").startswith("audio/") and not audio.filename.lower().endswith((".wav", ".mp3", ".flac", ".m4a", ".ogg")):
        raise HTTPException(415, "Bitte eine Audiodatei hochladen (WAV, MP3, FLAC, M4A, OGG).")
    data = await audio.read()
    if len(data) > 60 * 1024 * 1024:
        raise HTTPException(413, "Datei zu groß (max. 60 MB).")
    engine = make_engine(db.get_settings())
    try:
        result = await engine.analyze(data, audio.filename or "upload")
    except EngineError as e:
        raise HTTPException(502, str(e) or "Analyse fehlgeschlagen") from e
    return {
        "caption": result.get("caption", ""),
        "lyrics": result.get("lyrics", ""),
        "bpm": result.get("bpm") or 0,
        "keyscale": result.get("keyscale") or "",
        "timesignature": result.get("timesignature") or "",
        "vocal_language": result.get("vocal_language") or "",
        "duration": result.get("duration") or 0,
    }


@app.get("/api/health")
async def health():
    s = db.get_settings()
    try:
        return {"engine": s["engine"], **(await make_engine(s).health())}
    except Exception as e:  # noqa: BLE001
        return {"engine": s["engine"], "ok": False, "error": str(e) or e.__class__.__name__}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
