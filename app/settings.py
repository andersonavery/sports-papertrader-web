import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

POLY_SKILLS_DIR = Path(os.getenv("POLY_SKILLS_DIR", "~/.copilot/skills/polymarket-api")).expanduser()
DB_PATH = POLY_SKILLS_DIR / "paper_trades.db"
