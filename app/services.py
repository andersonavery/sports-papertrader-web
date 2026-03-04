import subprocess
import sys
import fcntl
from pathlib import Path
from app.settings import POLY_SKILLS_DIR

LOCK_PATH = POLY_SKILLS_DIR / ".web_lock"


def _run_script(script_name, *args):
    """Run a Python script in the skills directory with file locking."""
    script = POLY_SKILLS_DIR / script_name
    if not script.exists():
        return False, f"Script not found: {script}"

    LOCK_PATH.touch(exist_ok=True)
    with open(LOCK_PATH, "w") as lock_file:
        try:
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False, "Another operation is already running. Please wait."

        try:
            result = subprocess.run(
                [sys.executable, str(script)] + list(args),
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(POLY_SKILLS_DIR),
            )
            output = result.stdout + result.stderr
            success = result.returncode == 0
            return success, output.strip()
        except subprocess.TimeoutExpired:
            return False, "Operation timed out (120s limit)."
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def run_scan(league=None):
    args = ["scan"]
    if league:
        args += ["--league", league]
    return _run_script("paper_trader.py", *args)


def run_resolve():
    return _run_script("paper_trader.py", "resolve")


def run_update_elo():
    return _run_script("elo_model.py", "update")


def run_full_update():
    """Update Elo then scan."""
    ok1, out1 = run_update_elo()
    ok2, out2 = run_scan()
    return ok1 and ok2, f"{out1}\n\n{out2}"
