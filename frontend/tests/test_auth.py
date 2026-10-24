from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core import db
from core.auth import (
    GENERIC_LOGIN_ERROR,
    AuthError,
    hash_password,
    is_locked,
    login,
    signup,
    verify_password,
)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "app.db"
    db.init_db(path)
    return path


def test_hash_and_verify_password():
    hashed = hash_password("secret-pass")
    assert hashed != "secret-pass"
    assert verify_password("secret-pass", hashed)
    assert not verify_password("wrong", hashed)


def test_signup_and_login(db_path: Path):
    user = signup("alice", "password1", "password1", "Alice", db_path=db_path)
    assert user["username"] == "alice"
    assert "password" not in user
    again = login("alice", "password1", db_path=db_path)
    assert again["id"] == user["id"]


def test_signup_rejects_taken_username(db_path: Path):
    signup("alice", "password1", "password1", db_path=db_path)
    with pytest.raises(AuthError, match="already taken"):
        signup("Alice", "password1", "password1", db_path=db_path)


def test_login_generic_error(db_path: Path):
    signup("alice", "password1", "password1", db_path=db_path)
    with pytest.raises(AuthError, match=GENERIC_LOGIN_ERROR):
        login("alice", "nope-nope", db_path=db_path)
    with pytest.raises(AuthError, match=GENERIC_LOGIN_ERROR):
        login("nobody", "password1", db_path=db_path)


def test_lockout_after_five_failures(db_path: Path):
    signup("alice", "password1", "password1", db_path=db_path)
    for _ in range(5):
        with pytest.raises(AuthError, match=GENERIC_LOGIN_ERROR):
            login("alice", "wrongpass", db_path=db_path)
    stored = db.get_user_by_username("alice", db_path=db_path)
    assert stored is not None
    assert stored["failed_logins"] == 5
    assert is_locked(stored)
    with pytest.raises(AuthError, match=GENERIC_LOGIN_ERROR):
        login("alice", "password1", db_path=db_path)

    stored["locked_until"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    db.update_login_failure(stored["id"], 5, stored["locked_until"], db_path=db_path)
    user = login("alice", "password1", db_path=db_path)
    assert user["username"] == "alice"
    refreshed = db.get_user_by_username("alice", db_path=db_path)
    assert refreshed["failed_logins"] == 0
