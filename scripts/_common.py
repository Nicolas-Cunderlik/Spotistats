"""Shared helpers for the utility scripts: repo paths, venv interpreters, and
whether a pipeline stage is running. Standard library only, so any Python
can run the scripts - each one hands real work to the right venv."""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
APP_VENV = REPO / ".venv"
RESEARCH = REPO / "research" / "stem_similarity"
RESEARCH_VENV = RESEARCH / ".venv"
RESEARCH_DATA = RESEARCH / "data"
LOCK_DIR = RESEARCH_DATA / "locks"
LOG_DIR = RESEARCH_DATA / "logs"


def venv_python(venv):
    """The interpreter inside `venv`, or exit with a setup hint if it's missing."""
    for candidate in (venv / "Scripts" / "python.exe", venv / "bin" / "python"):
        if candidate.exists():
            return str(candidate)
    hint = (
        'python -m venv .venv && .venv\\Scripts\\pip install -e ".[dev]"'
        if venv == APP_VENV
        else "see research/stem_similarity/requirements.txt"
    )
    sys.exit(f"No virtualenv at {venv} - create it first ({hint})")


def run(args, cwd=REPO, env=None):
    """Runs a command in the foreground; returns its exit code."""
    return subprocess.call(args, cwd=cwd, env=env)  # noqa: S603 - fixed commands built by these scripts


def running_stages():
    """Names of pipeline stages currently holding their lock (see
    stemsim.registry.exclusive). A lock the OS still holds means the stage's
    process is alive; a leftover lock file from a finished run doesn't count."""
    held = []
    for path in sorted(LOCK_DIR.glob("*.lock")) if LOCK_DIR.exists() else []:
        try:
            with open(path, "a+") as handle:
                if _try_lock(handle):
                    _unlock(handle)
                else:
                    held.append(path.stem)
        except OSError:
            held.append(path.stem)
    return held


if sys.platform == "win32":
    import msvcrt

    def _try_lock(handle):
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _unlock(handle):
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _try_lock(handle):
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _unlock(handle):
        fcntl.flock(handle, fcntl.LOCK_UN)
