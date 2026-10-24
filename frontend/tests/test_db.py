import sqlite3
from pathlib import Path

import pytest

from core import db


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "app.db"
    db.init_db(path)
    return path


def _user(db_path: Path, username: str = "alice") -> dict:
    return db.create_user(username, "hash", display_name=username.title(), db_path=db_path)


def test_subject_uniqueness(db_path: Path):
    user = _user(db_path)
    db.create_subject(user["id"], "Physics", "physics", db_path=db_path)
    with pytest.raises(sqlite3.IntegrityError):
        db.create_subject(user["id"], "Physics again", "physics", db_path=db_path)


def test_same_slug_ok_for_other_user(db_path: Path):
    alice = _user(db_path, "alice")
    bob = _user(db_path, "bob")
    db.create_subject(alice["id"], "Physics", "physics", db_path=db_path)
    db.create_subject(bob["id"], "Physics", "physics", db_path=db_path)
    assert db.subject_slug_exists(alice["id"], "physics", db_path=db_path)
    alice_subjects = db.list_subjects(alice["id"], db_path=db_path)
    bob_subjects = db.list_subjects(bob["id"], db_path=db_path)
    assert len(alice_subjects) == 1
    assert len(bob_subjects) == 1
    assert alice_subjects[0]["id"] != bob_subjects[0]["id"]


def test_queries_are_scoped_to_user(db_path: Path):
    alice = _user(db_path, "alice")
    bob = _user(db_path, "bob")
    a_sub = db.create_subject(alice["id"], "Chem", "chem", db_path=db_path)
    b_sub = db.create_subject(bob["id"], "Chem", "chem", db_path=db_path)
    db.insert_document(
        doc_id="doc-a",
        user_id=alice["id"],
        subject_id=a_sub["id"],
        filename="a.pdf",
        size_bytes=10,
        sha256="aaa",
        status="ready",
        db_path=db_path,
    )
    db.insert_document(
        doc_id="doc-b",
        user_id=bob["id"],
        subject_id=b_sub["id"],
        filename="b.pdf",
        size_bytes=10,
        sha256="bbb",
        status="ready",
        db_path=db_path,
    )
    db.insert_message(
        user_id=alice["id"],
        subject_id=a_sub["id"],
        role="user",
        content="alice secret",
        db_path=db_path,
    )
    db.insert_message(
        user_id=bob["id"],
        subject_id=b_sub["id"],
        role="user",
        content="bob secret",
        db_path=db_path,
    )

    assert db.get_subject(bob["id"], a_sub["id"], db_path=db_path) is None
    assert db.get_document(bob["id"], "doc-a", db_path=db_path) is None
    assert db.list_documents(bob["id"], a_sub["id"], db_path=db_path) == []
    msgs = db.list_messages(bob["id"], a_sub["id"], db_path=db_path)
    assert msgs == []
    bob_msgs = db.list_messages(bob["id"], b_sub["id"], db_path=db_path)
    assert bob_msgs[0]["content"] == "bob secret"


def test_clear_messages_only_for_that_subject(db_path: Path):
    alice = _user(db_path)
    s1 = db.create_subject(alice["id"], "A", "a", db_path=db_path)
    s2 = db.create_subject(alice["id"], "B", "b", db_path=db_path)
    db.insert_message(user_id=alice["id"], subject_id=s1["id"], role="user", content="one", db_path=db_path)
    db.insert_message(user_id=alice["id"], subject_id=s2["id"], role="user", content="two", db_path=db_path)
    db.clear_messages(alice["id"], s1["id"], db_path=db_path)
    assert db.list_messages(alice["id"], s1["id"], db_path=db_path) == []
    assert len(db.list_messages(alice["id"], s2["id"], db_path=db_path)) == 1
