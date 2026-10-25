from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import streamlit as st

from core import api_client, db
from core.api_client import ApiError
from core.config import MAX_UPLOAD_MB, POLL_SECONDS
from core.db import new_id
from core.text_utils import format_size, safe_filename

ACCEPTED = ["pdf", "docx", "pptx", "txt", "md","doc"]
LONG_PROCESSING_MINUTES = 15
UNKNOWN_TOOLTIP = "The server no longer knows this document. It may need to be uploaded again."


def render_documents(user: dict, subject: dict) -> None:
    st.subheader("Documents")
    st.caption("Upload files for this subject. Processing can take a few seconds to a few minutes.")

    files = st.file_uploader(
        "Choose files",
        type=ACCEPTED,
        accept_multiple_files=True,
        key=f"uploader_{subject['id']}",
    )
    upload_anyway = st.checkbox(
        "Upload anyway if this file was already added",
        key=f"anyway_{subject['id']}",
    )
    if st.button("Process", type="primary"):
        _process_files(user, subject, files or [], upload_anyway)

    docs = db.list_documents(user["id"], subject["id"])
    processing = [d for d in docs if d["status"] == "processing"]
    if processing:
        _poll_statuses(user["id"], subject["id"])
        docs = db.list_documents(user["id"], subject["id"])

    if not docs:
        st.info("No documents in this subject yet.")
        return

    rows = []
    for doc in docs:
        status = _status_label(doc)
        error = doc.get("error") or ""
        if doc["status"] == "unknown" and not error:
            error = UNKNOWN_TOOLTIP
        rows.append(
            {
                "Filename": doc["filename"],
                "Size": format_size(doc.get("size_bytes")),
                "Status": status,
                "Uploaded": _short_time(doc.get("created_at")),
                "Error": error,
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)


def _status_label(doc: dict) -> str:
    status = doc["status"]
    if status == "processing" and _is_overdue(doc.get("created_at")):
        return "processing (taking unusually long)"
    return status


def _is_overdue(created_at: str | None) -> bool:
    if not created_at:
        return False
    try:
        started = datetime.fromisoformat(created_at)
    except ValueError:
        return False
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - started
    return age.total_seconds() > LONG_PROCESSING_MINUTES * 60


def _short_time(value: str | None) -> str:
    if not value:
        return ""
    return value.replace("T", " ")[:19]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _process_files(user: dict, subject: dict, files: list, upload_anyway: bool) -> None:
    if not files:
        st.warning("Choose at least one file first.")
        return
    max_bytes = MAX_UPLOAD_MB * 1024 * 1024
    for uploaded in files:
        filename = safe_filename(uploaded.name)
        data = uploaded.getvalue()
        if len(data) > max_bytes:
            st.error(f"{filename} is larger than {MAX_UPLOAD_MB} MB.")
            continue
        digest = _sha256(data)
        existing = db.find_document_by_hash(user["id"], subject["id"], digest)
        if existing and not upload_anyway:
            st.warning(f"{filename} is already in this subject. Tick “Upload anyway” to send it again.")
            continue
        doc_id = new_id()
        db.insert_document(
            doc_id=doc_id,
            user_id=user["id"],
            subject_id=subject["id"],
            filename=filename,
            size_bytes=len(data),
            sha256=digest,
            status="uploading",
        )
        try:
            api_client.upload(
                file_bytes=data,
                filename=filename,
                user_id=user["id"],
                subject=subject["slug"],
                doc_id=doc_id,
            )
            db.update_document_status(user["id"], doc_id, "processing")
        except ApiError as exc:
            db.update_document_status(user["id"], doc_id, "failed", error=exc.message)
            st.error(f"{filename}: {exc.message}")
    st.rerun()


@st.fragment(run_every=f"{POLL_SECONDS}s")
def _poll_statuses(user_id: str, subject_id: str) -> None:
    processing = db.list_processing_documents(user_id, subject_id)
    if not processing:
        return
    changed = False
    for doc in processing:
        try:
            result = api_client.get_status(doc["id"])
            if result.status != doc["status"] or result.error != doc.get("error"):
                db.update_document_status(
                    user_id,
                    doc["id"],
                    result.status,
                    error=result.error,
                )
                changed = True
        except ApiError as exc:
            if exc.status_code == 404:
                db.update_document_status(
                    user_id,
                    doc["id"],
                    "unknown",
                    error=UNKNOWN_TOOLTIP,
                )
                changed = True
            else:
                st.warning(exc.message)
    if changed:
        st.rerun()
