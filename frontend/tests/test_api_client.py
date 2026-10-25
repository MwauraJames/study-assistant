from unittest.mock import Mock

import pytest
import requests

from core import api_client
from core.api_client import ApiError, AskResult, ChatSummary


def _response(status_code: int, payload: dict | None = None, url: str = "http://localhost:8000/x") -> Mock:
    resp = Mock()
    resp.status_code = status_code
    resp.url = url
    resp.json.return_value = payload or {}
    return resp


def test_ask_always_sends_subject(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _response(200, {"answer": "ok 【source】"})

    monkeypatch.setattr(api_client._session, "post", fake_post)
    result = api_client.ask("What is force?", "user-1", "physics")
    assert isinstance(result, AskResult)
    assert captured["json"]["subject"] == "physics"
    assert captured["json"]["user_id"] == "user-1"
    assert "subject" in captured["json"]
    assert "chat_id" not in captured["json"]


def test_ask_requires_subject():
    with pytest.raises(ApiError, match="subject"):
        api_client.ask("q", "user-1", "")


def test_error_mapping_timeout(monkeypatch):
    monkeypatch.setattr(
        api_client._session,
        "post",
        Mock(side_effect=requests.Timeout()),
    )
    with pytest.raises(ApiError, match="too long"):
        api_client.ask("q", "u", "physics")


def test_error_mapping_connection(monkeypatch):
    monkeypatch.setattr(
        api_client._session,
        "post",
        Mock(side_effect=requests.ConnectionError()),
    )
    with pytest.raises(ApiError, match="Cannot reach the server"):
        api_client.upload(b"x", "a.txt", "u", "physics", "doc")


def test_upload_does_not_retry(monkeypatch):
    post = Mock(side_effect=requests.ConnectionError())
    monkeypatch.setattr(api_client._session, "post", post)
    with pytest.raises(ApiError):
        api_client.upload(b"x", "a.txt", "u", "physics", "doc")
    assert post.call_count == 1


def test_status_retries_connection_once(monkeypatch):
    get = Mock(
        side_effect=[
            requests.ConnectionError(),
            _response(200, {"doc_id": "d", "status": "ready", "error": None}),
        ]
    )
    monkeypatch.setattr(api_client._session, "get", get)
    result = api_client.get_status("d")
    assert result.status == "ready"
    assert get.call_count == 2


def test_status_404(monkeypatch):
    monkeypatch.setattr(
        api_client._session,
        "get",
        Mock(return_value=_response(404, url="http://localhost:8000/status/d")),
    )
    with pytest.raises(ApiError) as exc:
        api_client.get_status("d")
    assert exc.value.status_code == 404


def test_ask_409(monkeypatch):
    monkeypatch.setattr(
        api_client._session,
        "post",
        Mock(return_value=_response(409)),
    )
    with pytest.raises(ApiError, match="still processing"):
        api_client.ask("q", "u", "physics", doc_id="d")


def test_ask_422_and_500(monkeypatch):
    monkeypatch.setattr(api_client._session, "post", Mock(return_value=_response(422)))
    with pytest.raises(ApiError, match="rejected"):
        api_client.ask("q", "u", "physics")
    monkeypatch.setattr(api_client._session, "post", Mock(return_value=_response(500)))
    with pytest.raises(ApiError, match="server"):
        api_client.ask("q", "u", "physics")


def test_ask_keeps_sources(monkeypatch):
    monkeypatch.setattr(
        api_client._session,
        "post",
        Mock(return_value=_response(200, {"answer": "hi", "sources": ["notes.pdf"]})),
    )
    result = api_client.ask("q", "u", "physics")
    assert result.sources == ["notes.pdf"]


def test_ask_sends_chat_id_and_returns_it(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None):
        captured["json"] = json
        return _response(200, {"answer": "ok", "chat_id": "chat-123"})

    monkeypatch.setattr(api_client._session, "post", fake_post)
    result = api_client.ask("follow up", "user-1", "physics", chat_id="chat-123")
    assert captured["json"]["chat_id"] == "chat-123"
    assert result.chat_id == "chat-123"


def test_list_chats_and_messages(monkeypatch):
    def fake_get(url, params=None, timeout=None):
        if url.endswith("/chats/user-1"):
            assert params == {"subject": "physics"}
            return _response(
                200,
                {
                    "chats": [
                        {"chat_id": "c1", "title": "Newton", "subject": "physics"},
                    ]
                },
            )
        return _response(
            200,
            {
                "chat_id": "c1",
                "messages": [
                    {"role": "user", "content": "What is force?"},
                    {"role": "assistant", "content": "A push or pull."},
                ],
            },
        )

    monkeypatch.setattr(api_client._session, "get", fake_get)
    chats = api_client.list_chats("user-1", "physics")
    assert chats == [
        ChatSummary(chat_id="c1", title="Newton", subject="physics", updated_at=None)
    ]
    messages = api_client.get_chat_messages("c1")
    assert messages[0]["role"] == "user"
    assert messages[1]["content"] == "A push or pull."
