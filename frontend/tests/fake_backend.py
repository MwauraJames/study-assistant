from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

app = FastAPI()

# doc_id -> {user_id, subject, status, error, filename}
documents: dict[str, dict] = {}
chats: dict[str, dict] = {}
messages: dict[str, list[dict]] = {}


class Question(BaseModel):
    query: str
    user_id: str
    subject: Optional[str] = None
    doc_id: Optional[str] = None
    chat_id: Optional[str] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finish_upload(doc_id: str, filename: str) -> None:
    time.sleep(5)
    record = documents.get(doc_id)
    if record is None:
        return
    if "fail" in (filename or "").lower():
        record["status"] = "failed"
        record["error"] = "Ingestion failed (filename contains 'fail')."
    else:
        record["status"] = "ready"
        record["error"] = None


@app.post("/upload", status_code=202)
def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str = Form(...),
    subject: str = Form(...),
    doc_id: Optional[str] = Form(None),
):
    doc_id = doc_id or str(uuid.uuid4())
    filename = file.filename or "upload"
    documents[doc_id] = {
        "user_id": user_id,
        "subject": subject,
        "status": "processing",
        "error": None,
        "filename": filename,
    }
    background_tasks.add_task(_finish_upload, doc_id, filename)
    return {
        "doc_id": doc_id,
        "user_id": user_id,
        "subject": subject,
        "status": "processing",
    }


@app.get("/status/{doc_id}")
def get_status(doc_id: str):
    record = documents.get(doc_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Unknown doc_id: {doc_id}")
    return {
        "doc_id": doc_id,
        "status": record["status"],
        "error": record["error"],
    }


@app.post("/ask")
def ask(body: Question):
    if body.doc_id:
        record = documents.get(body.doc_id)
        if record and record.get("status") == "processing":
            raise HTTPException(
                status_code=409,
                detail=f"Document {body.doc_id} is still processing.",
            )
    time.sleep(2)

    def matches(doc: dict, doc_id: str | None = None) -> bool:
        if doc["user_id"] != body.user_id:
            return False
        if body.subject is not None and doc["subject"] != body.subject:
            return False
        if doc["status"] != "ready":
            return False
        if body.doc_id and doc_id != body.doc_id:
            return False
        return True

    matching = [
        doc for doc_id, doc in documents.items() if matches(doc, doc_id)
    ]
    if not matching:
        answer = "nothing found"
    else:
        subject = body.subject or matching[0]["subject"]
        answer = f"Here is what I found for {subject}. 【source】"

    chat_id = body.chat_id or str(uuid.uuid4())
    now = _now()
    if chat_id not in chats:
        chats[chat_id] = {
            "chat_id": chat_id,
            "user_id": body.user_id,
            "subject": body.subject,
            "title": (body.query or "")[:60],
            "created_at": now,
            "updated_at": now,
        }
        messages[chat_id] = []
    chats[chat_id]["updated_at"] = now
    messages[chat_id].append({"role": "user", "content": body.query, "created_at": now})
    messages[chat_id].append({"role": "assistant", "content": answer, "created_at": now})
    return {"chat_id": chat_id, "answer": answer}


@app.get("/chats/{chat_id}/messages")
def get_chat_history(chat_id: str):
    return {"chat_id": chat_id, "messages": messages.get(chat_id, [])}


@app.get("/chats/{user_id}")
def get_user_chats(user_id: str, subject: Optional[str] = None):
    found = []
    for chat in chats.values():
        if chat["user_id"] != user_id:
            continue
        if subject is not None and chat.get("subject") != subject:
            continue
        found.append(chat)
    found.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return {"chats": found}
