from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from core import db
from core.api_client import AskResult, ChatSummary, StatusResult, UploadResult
from core.auth import signup
from core.text_utils import clean_answer

APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture
def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_file = tmp_path / "app.db"
    monkeypatch.setattr("core.config.DB_PATH", db_file)
    monkeypatch.setattr("core.db.DB_PATH", db_file)
    db.init_db(db_file)
    return db_file


def _mock_backend(monkeypatch: pytest.MonkeyPatch, asks: list) -> dict:
    monkeypatch.setattr("core.api_client.ping", lambda: True)
    store: dict[str, dict] = {"chats": {}, "messages": {}}

    def fake_upload(file_bytes, filename, user_id, subject, doc_id):
        return UploadResult(doc_id=doc_id, user_id=user_id, subject=subject, status="processing")

    def fake_status(doc_id):
        return StatusResult(doc_id=doc_id, status="ready", error=None)

    def fake_ask(query, user_id, subject, doc_id=None, chat_id=None):
        assert subject, "frontend must always send a subject"
        asks.append(
            {
                "query": query,
                "user_id": user_id,
                "subject": subject,
                "doc_id": doc_id,
                "chat_id": chat_id,
            }
        )
        cid = chat_id or f"chat-{subject}"
        if cid not in store["chats"]:
            store["chats"][cid] = ChatSummary(
                chat_id=cid,
                title=query[:60],
                subject=subject,
            )
            store["messages"][cid] = []
        store["messages"][cid].append({"role": "user", "content": query})
        answer = f"Reply for {subject} 【source】"
        store["messages"][cid].append({"role": "assistant", "content": answer})
        return AskResult(answer=answer, chat_id=cid)

    def fake_list_chats(user_id, subject=None):
        return [
            chat
            for chat in store["chats"].values()
            if subject is None or chat.subject == subject
        ]

    def fake_get_messages(chat_id):
        return list(store["messages"].get(chat_id, []))

    monkeypatch.setattr("core.api_client.upload", fake_upload)
    monkeypatch.setattr("core.api_client.get_status", fake_status)
    monkeypatch.setattr("core.api_client.ask", fake_ask)
    monkeypatch.setattr("core.api_client.list_chats", fake_list_chats)
    monkeypatch.setattr("core.api_client.get_chat_messages", fake_get_messages)
    return store


def test_signup_subject_chat_histories_are_separate(isolated_db: Path, monkeypatch: pytest.MonkeyPatch):
    asks: list = []
    store = _mock_backend(monkeypatch, asks)

    user = signup("alice", "password1", "password1", "Alice", db_path=isolated_db)
    physics = db.create_subject(user["id"], "Physics", "physics", db_path=isolated_db)
    chem = db.create_subject(user["id"], "Chemistry", "chemistry", db_path=isolated_db)
    db.insert_document(
        doc_id="doc-p",
        user_id=user["id"],
        subject_id=physics["id"],
        filename="mechanics.pdf",
        size_bytes=12,
        sha256="p",
        status="ready",
        db_path=isolated_db,
    )
    db.insert_document(
        doc_id="doc-c",
        user_id=user["id"],
        subject_id=chem["id"],
        filename="bonds.pdf",
        size_bytes=12,
        sha256="c",
        status="ready",
        db_path=isolated_db,
    )

    at = AppTest.from_file(str(APP_PATH), default_timeout=15)
    at.session_state["user"] = user
    at.session_state["subject_id"] = physics["id"]
    at.run()
    assert not at.exception

    at.chat_input[0].set_value("What is force?").run()
    assert not at.exception
    assert asks[-1]["subject"] == "physics"
    assert asks[-1]["chat_id"] is None
    physics_chat = f"chat-{physics['slug']}"
    assert at.session_state[f"active_chat_{physics['id']}"] == physics_chat
    physics_msgs = store["messages"][physics_chat]
    assert physics_msgs[0]["content"] == "What is force?"
    assert "【" in physics_msgs[1]["content"]
    assert "【" not in clean_answer(physics_msgs[1]["content"])

    at.chat_input[0].set_value("And gravity?").run()
    assert not at.exception
    assert asks[-1]["chat_id"] == physics_chat

    at.session_state["subject_id"] = chem["id"]
    at.session_state["subject_radio"] = chem["id"]
    at.run()
    at.chat_input[0].set_value("What is a bond?").run()
    assert asks[-1]["subject"] == "chemistry"
    assert asks[-1]["chat_id"] is None
    chem_chat = f"chat-{chem['slug']}"
    chem_msgs = store["messages"][chem_chat]
    assert [m["content"] for m in chem_msgs if m["role"] == "user"] == ["What is a bond?"]

    at.session_state["subject_id"] = physics["id"]
    at.session_state["subject_radio"] = physics["id"]
    at.run()
    physics_again = store["messages"][physics_chat]
    assert [m["content"] for m in physics_again if m["role"] == "user"] == [
        "What is force?",
        "And gravity?",
    ]
    chem_again = store["messages"][chem_chat]
    assert [m["content"] for m in chem_again if m["role"] == "user"] == ["What is a bond?"]


def test_signup_form_creates_session_user(isolated_db: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("core.api_client.ping", lambda: True)
    at = AppTest.from_file(str(APP_PATH), default_timeout=15)
    at.run()
    assert not at.exception
    signup_tab = at.tabs[1]
    signup_tab.text_input[0].set_value("bob_user")
    signup_tab.text_input[1].set_value("Bob")
    signup_tab.text_input[2].set_value("password1")
    signup_tab.text_input[3].set_value("password1")
    signup_tab.form_submit_button[0].click().run()
    assert not at.exception
    assert at.session_state["user"]["username"] == "bob_user"
