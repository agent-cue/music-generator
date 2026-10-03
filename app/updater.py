"""Updates aus dem GitHub-Repository: prüfen, holen, neu starten."""
import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request

from . import db

ROOT = Path(__file__).resolve().parent.parent
BRANCH = "main"
REPO_URL = "https://github.com/agent-cue/music-generator.git"
router = APIRouter(prefix="/api/update")


def tr(lang: str, de: str, en: str) -> str:
    return en if lang == "en" else de


def git(*args: str, timeout: int = 60) -> str:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}   # nie nach Passwort fragen
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout, env=env)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout).strip() or f"git {args[0]} fehlgeschlagen")
    return r.stdout.strip()


def _has_head() -> bool:
    """Git-Ordner mit mindestens einem Commit? (Falsch auch nach einer abgebrochenen Umstellung auf Git.)"""
    if not (ROOT / ".git").exists():
        return False
    try:
        git("rev-parse", "--verify", "--quiet", "HEAD")
        return True
    except RuntimeError:
        return False


def _status(lang: str = "de") -> dict:
    if not _has_head():
        # Ohne Git installiert (z. B. als ZIP geladen): Version unbekannt, das Update stellt auf Git um
        latest = git("ls-remote", REPO_URL, BRANCH, timeout=30).split()
        if not latest:
            raise RuntimeError(tr(lang, "GitHub ist nicht erreichbar (Internetverbindung?).", "GitHub is not reachable (internet connection?)."))
        return {"current": "?", "latest": latest[0][:7], "behind": 1, "ahead": 0, "dirty": False, "needs_install": False, "nogit": True,
                "changes": [tr(lang, "Neue Fassung von GitHub. Die Installation wird dabei auf Git-Updates umgestellt.",
                               "Latest version from GitHub. The installation is switched to Git updates.")]}
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
async def check(x_lang: str = Header("de")):
    try:
        return {"ok": True, **await asyncio.to_thread(_status, x_lang)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": _friendly(e, x_lang)}


def _friendly(e: Exception, lang: str = "de") -> str:
    msg = str(e) or e.__class__.__name__
    if isinstance(e, subprocess.TimeoutExpired):
        return tr(lang, "Keine Antwort von GitHub (Internetverbindung?).", "No response from GitHub (internet connection?).")
    if "Could not resolve" in msg or "unable to access" in msg:
        return tr(lang, "GitHub ist nicht erreichbar (Internetverbindung?).", "GitHub is not reachable (internet connection?).")
    return msg


def _apply(lang: str = "de") -> dict:
    s = _status(lang)
    if not s["behind"]:
        raise RuntimeError(tr(lang, "Du hast bereits die aktuelle Version.", "You already have the latest version."))
    if s["dirty"]:
        raise RuntimeError(tr(lang, "Im Programmordner gibt es eigene Änderungen an Dateien. Das Update würde sie überschreiben.", "There are local changes to files in the program folder. The update would overwrite them."))
    if s["ahead"]:
        raise RuntimeError(tr(lang, "Diese Installation hat eigene Commits, die nicht auf GitHub sind. Automatisch geht das nicht.", "This installation has its own commits that are not on GitHub. Not possible automatically."))
    if s.get("nogit"):
        return _apply_nogit(s)
    before = git("rev-parse", "HEAD")
    git("pull", "--ff-only", "--quiet", "origin", BRANCH, timeout=120)
    if {"pyproject.toml", "uv.lock"} & set(git("diff", "--name-only", before, "HEAD").splitlines()):
        subprocess.run(["uv", "sync", "--quiet"], cwd=ROOT, check=True, timeout=300)
    return {**s, "current": git("rev-parse", "--short", "HEAD")}


def _apply_nogit(s: dict) -> dict:
    """Ordner ohne .git in ein Git-Repository verwandeln und auf den neuesten Stand bringen.
    data/, engine/ und .venv sind in .gitignore und bleiben unberührt."""
    def acestep_rev() -> str:
        try:
            return next(l for l in (ROOT / "scripts" / "common.sh").read_text().splitlines() if l.startswith("ACESTEP_REV="))
        except (OSError, StopIteration):
            return ""
    old_rev = acestep_rev()
    if not (ROOT / ".git").exists():
        git("init", "-q", "-b", BRANCH)
    if "origin" not in git("remote").split():
        git("remote", "add", "origin", REPO_URL)
    git("fetch", "--quiet", "origin", BRANCH, timeout=120)
    git("checkout", "--quiet", "-B", BRANCH, f"origin/{BRANCH}", "--force")
    git("branch", "--set-upstream-to", f"origin/{BRANCH}", BRANCH)
    subprocess.run(["uv", "sync", "--quiet"], cwd=ROOT, check=True, timeout=300)
    return {**s, "current": git("rev-parse", "--short", "HEAD"), "needs_install": acestep_rev() != old_rev}


@router.post("/apply")
async def apply(request: Request, x_lang: str = Header("de")):
    busy = db.one("SELECT COUNT(*) AS n FROM songs WHERE status IN ('queued','running')")["n"]
    if busy:
        raise HTTPException(409, tr(x_lang, "Es laufen noch Songs. Bitte erst fertig werden lassen oder abbrechen.", "Songs are still running. Please let them finish or cancel them first."))
    try:
        res = await asyncio.to_thread(_apply, x_lang)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, _friendly(e, x_lang)) from e
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
