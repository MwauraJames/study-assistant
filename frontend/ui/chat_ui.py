from __future__ import annotations

import streamlit as st

from core import api_client, db
from core.api_client import ApiError
from core.text_utils import clean_answer

MAX_QUESTION_LEN = 2000


def render_chat(user: dict, subject: dict) -> None:
    st.subheader(f"Chatting with: {subject['name']}")
    st.caption(
        "Answers use only the documents in this subject. "
        "Each question is answered on its own, with no memory of earlier messages."
    )

    ready = db.list_ready_documents(user["id"], subject["id"])
    processing = db.list_processing_documents(user["id"], subject["id"])

    doc_id = None
    with st.expander("Scope"):
        labels = ["All documents in this subject"] + [d["filename"] for d in ready]
        choice = st.selectbox("Answer using", labels, index=0)
        if choice != "All documents in this subject":
            match = next(d for d in ready if d["filename"] == choice)
            doc_id = match["id"]

    if st.button("Clear chat"):
        db.clear_messages(user["id"], subject["id"])
        st.rerun()

    messages = db.list_messages(user["id"], subject["id"])
    for msg in messages:
        with st.chat_message(msg["role"]):
            if msg["role"] == "assistant":
                st.markdown(clean_answer(msg["content"]))
            else:
                st.markdown(msg["content"])

    disabled = not ready
    if disabled:
        if processing:
            st.info("Chat is disabled until at least one document is ready. Some files are still processing.")
        else:
            st.info("Chat is disabled until this subject has a ready document.")

    prompt = st.chat_input(
        "Ask a question about these documents",
        disabled=disabled,
        max_chars=MAX_QUESTION_LEN,
    )
    if not prompt:
        return
    if len(prompt) > MAX_QUESTION_LEN:
        st.error(f"Questions can be at most {MAX_QUESTION_LEN} characters.")
        return

    db.insert_message(
        user_id=user["id"],
        subject_id=subject["id"],
        role="user",
        content=prompt,
        doc_id=doc_id,
    )
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            with st.spinner("Searching your documents..."):
                result = api_client.ask(
                    query=prompt,
                    user_id=user["id"],
                    subject=subject["slug"],
                    doc_id=doc_id,
                )
            st.markdown(clean_answer(result.answer))
            if result.sources:
                with st.expander("Sources"):
                    for source in result.sources:
                        st.markdown(str(source))
            db.insert_message(
                user_id=user["id"],
                subject_id=subject["id"],
                role="assistant",
                content=result.answer,
                doc_id=doc_id,
            )
        except ApiError as exc:
            st.error(exc.message)
