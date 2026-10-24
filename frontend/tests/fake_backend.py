from __future__ import annotations

import time
import uuid
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

app = FastAPI()

# doc_id -> {user_id, subject, status, error, filename}
documents: dict[str, dict] = {}


class Question(BaseModel):
    query: str
    user_id: str
    subject: Optional[str] = None
    doc_id: Optional[str] = None


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
        return {"answer": "nothing found"}
    subject = body.subject or matching[0]["subject"]
    return {"answer": f"Here is what I found for {subject}. 【source】"}
