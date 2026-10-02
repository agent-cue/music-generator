"""Updates aus dem GitHub-Repository: prüfen, holen, neu starten."""
import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from . import db

ROOT = Path(__file__).resolve().parent.parent
BRANCH = "main"
router = APIRouter(prefix="/api/update")


def git(*args: str, timeout: int = 60) -> str:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}   # nie nach Passwort fragen
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout, env=env)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout).strip() or f"git {args[0]} fehlgeschlagen")
    return r.stdout.strip()


def _status() -> dict:
    if not (ROOT / ".git").exists():
        raise RuntimeError("Dies ist keine Git-Installation. Updates gehen nur, wenn die App per git clone installiert wurde.")
    git("fetch", "--quiet", "origin", BRANCH, timeout=30)
    remote = f"origin/{BRANCH}"
    behind = int(git("rev-list", "--count", f"HEAD..{remote}"))
    ahead = int(git("rev-list", "--count", f"{remote}..HEAD"))
    changes = git("log", f"HEAD..{remote}", "--format=%s", "-n", "15").splitlines() if behind else []
    dirty = bool(git("status", "--porcelain", "--untracked-files=no"))
    changed_files = git("diff", "--name-only", f"HEAD..{remote}").splitlines() if behind else []
    return {
        "current": git("rev-parse", "--short", "HEAD"), "latest": git("rev-parse", "--short", remote),
        "behind": behind, "ahead": ahead, "changes": changes, "dirty": dirty,
        # Neue acestep.cpp-Version oder neue Pakete: der Installer muss danach noch einmal laufen
        "needs_install": "scripts/common.sh" in changed_files,
    }


@router.get("/check")
async def check():
    try:
        return {"ok": True, **await asyncio.to_thread(_status)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": _friendly(e)}


def _friendly(e: Exception) -> str:
    msg = str(e) or e.__class__.__name__
    if isinstance(e, subprocess.TimeoutExpired):
        return "Keine Antwort von GitHub (Internetverbindung?)."
    if "Could not resolve" in msg or "unable to access" in msg:
        return "GitHub ist nicht erreichbar (Internetverbindung?)."
    return msg


def _apply() -> dict:
    s = _status()
    if not s["behind"]:
        raise RuntimeError("Du hast bereits die aktuelle Version.")
    if s["dirty"]:
        raise RuntimeError("Im Programmordner gibt es eigene Änderungen an Dateien. Das Update würde sie überschreiben.")
    if s["ahead"]:
        raise RuntimeError("Diese Installation hat eigene Commits, die nicht auf GitHub sind. Automatisch geht das nicht.")
    before = git("rev-parse", "HEAD")
    git("pull", "--ff-only", "--quiet", "origin", BRANCH, timeout=120)
    if {"pyproject.toml", "uv.lock"} & set(git("diff", "--name-only", before, "HEAD").splitlines()):
        subprocess.run(["uv", "sync", "--quiet"], cwd=ROOT, check=True, timeout=300)
    return {**s, "current": git("rev-parse", "--short", "HEAD")}


@router.post("/apply")
async def apply(request: Request):
    busy = db.one("SELECT COUNT(*) AS n FROM songs WHERE status IN ('queued','running')")["n"]
    if busy:
        raise HTTPException(409, "Es laufen noch Songs. Bitte erst fertig werden lassen oder abbrechen.")
    try:
        res = await asyncio.to_thread(_apply)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, _friendly(e)) from e
    asyncio.get_running_loop().call_later(0.8, _restart, request.url.port or 8765)
    return {"ok": True, **res}


def _restart(port: int) -> None:
    """Neuen Server abgekoppelt starten, der wartet, bis der Port frei ist; dann diesen beenden."""
    log = open(ROOT / "data" / "server.log", "ab")
    script = f'while lsof -i :{port} -sTCP:LISTEN -t >/dev/null 2>&1; do sleep 0.3; done; ' \
             f'exec "{sys.executable}" -m uvicorn app.main:app --host 127.0.0.1 --port {port}'
    subprocess.Popen(["/bin/sh", "-c", script], cwd=ROOT, stdout=log, stderr=log,
                     stdin=subprocess.DEVNULL, start_new_session=True)
    os.kill(os.getpid(), signal.SIGTERM)
