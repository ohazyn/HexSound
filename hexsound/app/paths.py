import sys
from pathlib import Path

DATA_DIR = Path.home() / ".hexsound"

def resource(rel: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / rel
