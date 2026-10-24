from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import bcrypt
import sqlite3

from core import db

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")
MIN_PASSWORD_LEN = 8
MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 5
GENERIC_LOGIN_ERROR = "Wrong username or password"


class AuthError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def validate_username(username: str) -> str | None:
    if not USERNAME_RE.fullmatch(username or ""):
        return "Username must be 3 to 32 characters: letters, digits, or underscore."
    return None


def validate_password(password: str) -> str | None:
    if not password or len(password) < MIN_PASSWORD_LEN:
        return f"Password must be at least {MIN_PASSWORD_LEN} characters."
    return None


def public_user(user: dict[str, Any]) -> dict[str, str]:
    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": user.get("display_name") or user["username"],
    }


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def is_locked(user: dict[str, Any], now: datetime | None = None) -> bool:
    until = _parse_iso(user.get("locked_until"))
    if until is None:
        return False
    now = now or datetime.now(timezone.utc)
    return until > now


def signup(
    username: str,
    password: str,
    confirm_password: str,
    display_name: str | None = None,
    db_path: Path | None = None,
) -> dict[str, str]:
    username = (username or "").strip()
    display_name = (display_name or "").strip() or None
    error = validate_username(username)
    if error:
        raise AuthError(error)
    error = validate_password(password)
    if error:
        raise AuthError(error)
    if password != confirm_password:
        raise AuthError("Passwords do not match.")
    if db.get_user_by_username(username, db_path=db_path):
        raise AuthError("That username is already taken.")
    try:
        user = db.create_user(
            username=username,
            password_hash=hash_password(password),
            display_name=display_name,
            db_path=db_path,
        )
    except sqlite3.IntegrityError as exc:
        raise AuthError("That username is already taken.") from exc
    return public_user(user)


def login(
    username: str,
    password: str,
    db_path: Path | None = None,
) -> dict[str, str]:
    username = (username or "").strip()
    user = db.get_user_by_username(username, db_path=db_path)
    if user is None:
        raise AuthError(GENERIC_LOGIN_ERROR)
    if is_locked(user):
        raise AuthError(GENERIC_LOGIN_ERROR)
    if not verify_password(password, user["password_hash"]):
        failed = int(user["failed_logins"] or 0) + 1
        locked_until = None
        if failed >= MAX_FAILED_LOGINS:
            locked_until = (
                datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
            ).isoformat()
        db.update_login_failure(user["id"], failed, locked_until, db_path=db_path)
        raise AuthError(GENERIC_LOGIN_ERROR)
    db.reset_login_failures(user["id"], db_path=db_path)
    refreshed = db.get_user_by_id(user["id"], db_path=db_path) or user
    return public_user(refreshed)
