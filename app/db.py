"""SQLite-Speicher für Songs (Metadaten) und Einstellungen."""
import json
import sqlite3
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SONGS_DIR = DATA / "songs"
DB_PATH = DATA / "music.db"

def _engine_conf() -> dict:
    """Vom Installer geschrieben (data/engine.conf): MODE=single|split, LM_FILE=…"""
    conf = {}
    try:
        for line in (DATA / "engine.conf").read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                conf[k.strip()] = v.strip()
    except OSError:
        pass
    return conf


_conf = _engine_conf()

DEFAULT_SETTINGS = {
    "engine": "acestep_cpp",           # "acestep_cpp" oder "mock"
    "server_url": "http://127.0.0.1:8085",   # Synthese (DiT + VAE, Metal)
    # Sprachmodell: eigener CPU-Server (Modus split) oder leer = gleicher Server wie Synthese (single)
    "lm_url": "" if _conf.get("MODE") == "single" else "http://127.0.0.1:8086",
    "lm_model": _conf.get("LM_FILE", ""),     # leer = erstes Sprachmodell im Modellordner
    "poll_interval": 1.5,
    "timeout_minutes": 30,
}

_lock = threading.Lock()


def connect() -> sqlite3.Connection:
    DATA.mkdir(exist_ok=True)
    SONGS_DIR.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


_con = connect()


def init():
    with _lock:
        _con.executescript(
            """
            CREATE TABLE IF NOT EXISTS songs (
                id          TEXT PRIMARY KEY,
                group_id    TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                finished_at TEXT,
                status      TEXT NOT NULL,          -- queued | running | done | error | cancelled
                message     TEXT,
                title       TEXT,
                caption     TEXT NOT NULL,
                lyrics      TEXT,
                seed        INTEGER NOT NULL,
                params      TEXT NOT NULL,          -- JSON: vollständige Anfrage
                result_meta TEXT,                   -- JSON: vom Modell ergänzte Werte (bpm, key, lyrics …)
                engine      TEXT,
                file        TEXT,
                favorite    INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_songs_status ON songs(status);
            CREATE INDEX IF NOT EXISTS idx_songs_group ON songs(group_id);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """
        )
        # Nach einem Absturz hängengebliebene Jobs wieder einreihen
        _con.execute("UPDATE songs SET status='queued', message=NULL WHERE status='running'")
        _con.commit()


def execute(sql: str, args: tuple = ()) -> None:
    with _lock:
        _con.execute(sql, args)
        _con.commit()


def query(sql: str, args: tuple = ()) -> list[dict]:
    with _lock:
        return [dict(r) for r in _con.execute(sql, args).fetchall()]


def one(sql: str, args: tuple = ()) -> dict | None:
    rows = query(sql, args)
    return rows[0] if rows else None


def get_settings() -> dict:
    s = dict(DEFAULT_SETTINGS)
    for r in query("SELECT key, value FROM settings"):
        s[r["key"]] = json.loads(r["value"])
    return s


def save_settings(values: dict) -> dict:
    for k, v in values.items():
        if k in DEFAULT_SETTINGS:
            execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (k, json.dumps(v)),
            )
    return get_settings()
