from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

FRONTEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(FRONTEND_DIR / ".env")


def _bool(value: str, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
DB_PATH = Path(os.getenv("DB_PATH", str(FRONTEND_DIR / "data" / "app.db")))
if not DB_PATH.is_absolute():
    DB_PATH = (FRONTEND_DIR / DB_PATH).resolve()
MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", 25)
ASK_TIMEOUT_S = _int("ASK_TIMEOUT_S", 120)
UPLOAD_TIMEOUT_S = _int("UPLOAD_TIMEOUT_S", 120)
POLL_SECONDS = _int("POLL_SECONDS", 3)
ENABLE_DELETE = _bool(os.getenv("ENABLE_DELETE", "false"), default=False)


def ensure_data_dir() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
