"""FastAPI-Backend: Job-Queue, Bibliothek, Einstellungen."""
import asyncio
import json
import random
import re
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db, updater
from .engines import EngineError, make_engine

STATIC = db.ROOT / "static"
_wakeup = asyncio.Event()


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
            audio, ext, meta = await engine.generate(params, progress)
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


class SongPatch(BaseModel):
    favorite: bool | None = None
    title: str | None = None


def song_out(r: dict) -> dict:
    r["params"] = json.loads(r["params"])
    r["result_meta"] = json.loads(r["result_meta"]) if r["result_meta"] else None
    r["favorite"] = bool(r["favorite"])
    r["url"] = f"/api/songs/{r['id']}/audio" if r["file"] else None
    return r


# ---------------------------------------------------------------- API

@app.post("/api/generate")
def generate(req: GenerateRequest):
    group = req.group_id or uuid.uuid4().hex[:12]
    lyrics = "[Instrumental]" if req.instrumental else req.lyrics.strip()
    parts = [p.strip().strip(",") for p in (req.style, req.prompt) if p.strip()]
    caption = ", ".join(parts) if parts else req.caption.strip()
    if not caption:
        raise HTTPException(422, "Prompt oder Stil fehlt")
    base = req.model_dump(exclude={"variants", "group_id", "instrumental", "title", "keep_caption"})
    base["caption"] = caption
    base["use_cot_caption"] = not req.keep_caption
    base["lyrics"] = lyrics
    ids = []
    for i in range(req.variants):
        # Erste Variante nimmt den festen Seed, weitere zählen hoch -> alles reproduzierbar
        seed = random.randint(0, 2**31 - 1) if req.seed < 0 else req.seed + i
        params = {**base, "seed": seed}
        sid = uuid.uuid4().hex[:12]
        db.execute(
            "INSERT INTO songs(id, group_id, created_at, status, title, caption, lyrics, seed, params) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (sid, group, now(), "queued", req.title.strip() or None, caption, lyrics, seed, json.dumps(params)),
        )
        ids.append(sid)
    _wakeup.set()
    return {"group_id": group, "ids": ids}


@app.get("/api/songs")
def list_songs(q: str = "", favorites: bool = False, group: str = ""):
    sql, args = "SELECT * FROM songs WHERE 1=1", []
    if q:
        sql += " AND (caption LIKE ? OR lyrics LIKE ? OR title LIKE ?)"
        args += [f"%{q}%"] * 3
    if favorites:
        sql += " AND favorite=1"
    if group:
        sql += " AND group_id=?"
        args.append(group)
    sql += " ORDER BY created_at DESC, rowid DESC LIMIT 500"
    return [song_out(r) for r in db.query(sql, tuple(args))]


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
    return get_song(sid)


@app.post("/api/songs/{sid}/retry")
def retry_song(sid: str):
    db.execute("UPDATE songs SET status='queued', message=NULL WHERE id=? AND status IN ('error','cancelled')", (sid,))
    _wakeup.set()
    return get_song(sid)


@app.delete("/api/songs/{sid}")
def delete_song(sid: str):
    r = db.one("SELECT * FROM songs WHERE id=?", (sid,))
    if not r:
        raise HTTPException(404)
    if r["status"] == "queued":
        db.execute("UPDATE songs SET status='cancelled' WHERE id=?", (sid,))
        return {"cancelled": True}
    if r["status"] == "running":
        raise HTTPException(409, "Läuft gerade – bitte warten, bis der Job fertig ist.")
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


@app.get("/api/queue")
def queue():
    rows = db.query("SELECT id, status, message, caption FROM songs WHERE status IN ('queued','running') ORDER BY created_at, rowid")
    return {"running": [r for r in rows if r["status"] == "running"], "queued": len([r for r in rows if r["status"] == "queued"])}


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
