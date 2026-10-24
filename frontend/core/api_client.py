from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar

import requests

from core.config import API_URL, ASK_TIMEOUT_S, UPLOAD_TIMEOUT_S

logger = logging.getLogger("study_assistant.api")

CONNECT_TIMEOUT = 5
STATUS_READ_TIMEOUT = 10
PING_READ_TIMEOUT = 10

_session = requests.Session()

T = TypeVar("T")


class ApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass
class UploadResult:
    doc_id: str
    user_id: str
    subject: str
    status: str


@dataclass
class StatusResult:
    doc_id: str
    status: str
    error: str | None = None


@dataclass
class AskResult:
    answer: str
    sources: list[Any] | None = field(default=None)


def _friendly_http_error(response: requests.Response, *, for_status: bool = False) -> ApiError:
    code = response.status_code
    logger.warning("Backend HTTP %s on %s", code, response.url)
    if code == 404 and for_status:
        return ApiError("Unknown document.", status_code=404)
    if code == 409:
        return ApiError("That document is still processing.", status_code=409)
    if code == 422:
        return ApiError("The server rejected the request.", status_code=422)
    if 500 <= code <= 599:
        return ApiError("Something went wrong on the server.", status_code=code)
    if code == 404:
        return ApiError("Cannot reach the server. Is the backend running?", status_code=404)
    return ApiError("Something went wrong on the server.", status_code=code)


def _map_request_error(exc: Exception) -> ApiError:
    if isinstance(exc, requests.Timeout):
        logger.warning("Backend timeout: %s", type(exc).__name__)
        return ApiError("This is taking too long. Try again.")
    if isinstance(exc, requests.ConnectionError):
        logger.warning("Backend connection error: %s", type(exc).__name__)
        return ApiError("Cannot reach the server. Is the backend running?")
    logger.warning("Backend request failed: %s", type(exc).__name__)
    return ApiError("Cannot reach the server. Is the backend running?")


def _once_or_retry(fn: Callable[[], T], retry_connection: bool) -> T:
    try:
        return fn()
    except requests.ConnectionError:
        if retry_connection:
            return fn()
        raise


def upload(file_bytes: bytes, filename: str, user_id: str, subject: str, doc_id: str) -> UploadResult:
    def _do() -> requests.Response:
        files = {"file": (filename, file_bytes)}
        data = {"user_id": user_id, "subject": subject, "doc_id": doc_id}
        return _session.post(
            f"{API_URL}/upload",
            files=files,
            data=data,
            timeout=(CONNECT_TIMEOUT, UPLOAD_TIMEOUT_S),
        )

    try:
        response = _do()
    except Exception as exc:
        raise _map_request_error(exc) from exc
    if response.status_code >= 400:
        raise _friendly_http_error(response)
    payload = response.json()
    return UploadResult(
        doc_id=payload.get("doc_id", doc_id),
        user_id=payload.get("user_id", user_id),
        subject=payload.get("subject", subject),
        status=payload.get("status", "processing"),
    )


def get_status(doc_id: str) -> StatusResult:
    def _do() -> requests.Response:
        return _session.get(
            f"{API_URL}/status/{doc_id}",
            timeout=(CONNECT_TIMEOUT, STATUS_READ_TIMEOUT),
        )

    try:
        response = _once_or_retry(_do, retry_connection=True)
    except Exception as exc:
        raise _map_request_error(exc) from exc
    if response.status_code >= 400:
        raise _friendly_http_error(response, for_status=True)
    payload = response.json()
    return StatusResult(
        doc_id=payload.get("doc_id", doc_id),
        status=payload.get("status", "unknown"),
        error=payload.get("error"),
    )


def ask(query: str, user_id: str, subject: str, doc_id: str | None = None) -> AskResult:
    if not subject:
        raise ApiError("A subject is required.")
    payload: dict[str, Any] = {"query": query, "user_id": user_id, "subject": subject}
    if doc_id:
        payload["doc_id"] = doc_id

    def _do() -> requests.Response:
        return _session.post(
            f"{API_URL}/ask",
            json=payload,
            timeout=(CONNECT_TIMEOUT, ASK_TIMEOUT_S),
        )

    try:
        response = _do()
    except Exception as exc:
        raise _map_request_error(exc) from exc
    if response.status_code >= 400:
        raise _friendly_http_error(response)
    body = response.json()
    sources = body.get("sources")
    if not sources:
        sources = None
    return AskResult(answer=body.get("answer") or "", sources=sources)


def ping() -> bool:
    def _do() -> requests.Response:
        return _session.get(
            f"{API_URL}/",
            timeout=(CONNECT_TIMEOUT, PING_READ_TIMEOUT),
        )

    try:
        _once_or_retry(_do, retry_connection=True)
        return True
    except Exception as exc:
        logger.warning("Backend ping failed: %s", type(exc).__name__)
        return False
