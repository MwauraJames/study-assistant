from __future__ import annotations

import streamlit as st

from core import api_client, db
from core.api_client import ApiError, ChatSummary
from core.text_utils import clean_answer

MAX_QUESTION_LEN = 2000
NEW_CHAT = "__new__"


def _active_key(subject_id: str) -> str:
    return f"active_chat_{subject_id}"


def _select_key(subject_id: str) -> str:
    return f"chat_select_{subject_id}"


def _pending_key(subject_id: str) -> str:
    return f"pending_chat_{subject_id}"


def _get_active_chat_id(subject_id: str) -> str | None:
    value = st.session_state.get(_active_key(subject_id))
    if not value or value == NEW_CHAT:
        return None
    return str(value)


def _set_active_chat_id(subject_id: str, chat_id: str | None) -> None:
    value = chat_id or NEW_CHAT
    st.session_state[_active_key(subject_id)] = None if value == NEW_CHAT else value
    st.session_state[_pending_key(subject_id)] = value


def render_chat(user: dict, subject: dict) -> None:
    st.subheader(f"Chatting with: {subject['name']}")
    st.caption(
        "Answers use only the documents in this subject. "
        "Follow-up questions stay in this conversation so the assistant remembers earlier turns."
    )

    ready = db.list_ready_documents(user["id"], subject["id"])
    processing = db.list_processing_documents(user["id"], subject["id"])

    chats, chats_error = _load_chats(user["id"], subject["slug"])
    if chats_error:
        st.warning(chats_error)

    _render_conversation_controls(subject, chats)

    doc_id = None
    with st.expander("Scope"):
        labels = ["All documents in this subject"] + [d["filename"] for d in ready]
        choice = st.selectbox("Answer using", labels, index=0)
        if choice != "All documents in this subject":
            match = next(d for d in ready if d["filename"] == choice)
            doc_id = match["id"]

    chat_id = _get_active_chat_id(subject["id"])
    messages, messages_error = _load_messages(chat_id)
    if messages_error:
        st.error(messages_error)

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
                    chat_id=chat_id,
                )
            if result.chat_id:
                _set_active_chat_id(subject["id"], result.chat_id)
            st.markdown(clean_answer(result.answer))
            if result.sources:
                with st.expander("Sources"):
                    for source in result.sources:
                        st.markdown(str(source))
            st.rerun()
        except ApiError as exc:
            st.error(exc.message)


def _render_conversation_controls(subject: dict, chats: list[ChatSummary]) -> None:
    subject_id = subject["id"]
    active = _get_active_chat_id(subject_id)
    if active and not any(chat.chat_id == active for chat in chats):
        chats = [ChatSummary(chat_id=active, title="Current conversation"), *chats]
    options = [NEW_CHAT] + [chat.chat_id for chat in chats]
    labels = {NEW_CHAT: "New conversation"}
    for chat in chats:
        title = (chat.title or "Untitled").strip() or "Untitled"
        labels[chat.chat_id] = title

    select_key = _select_key(subject_id)
    pending_key = _pending_key(subject_id)
    if pending_key in st.session_state:
        pending = st.session_state.pop(pending_key)
        st.session_state[select_key] = pending if pending in options else NEW_CHAT
    elif select_key not in st.session_state:
        st.session_state[select_key] = active if active in options else NEW_CHAT
    elif st.session_state[select_key] not in options:
        st.session_state[select_key] = active if active in options else NEW_CHAT

    col_select, col_new = st.columns([4, 1])
    with col_select:
        chosen = st.selectbox(
            "Conversation",
            options,
            format_func=lambda value: labels.get(value, value),
            key=select_key,
        )
    with col_new:
        if st.button("New chat", width="stretch"):
            _set_active_chat_id(subject_id, None)
            st.rerun()

    st.session_state[_active_key(subject_id)] = None if chosen == NEW_CHAT else chosen


def _load_chats(user_id: str, subject_slug: str) -> tuple[list[ChatSummary], str | None]:
    try:
        return api_client.list_chats(user_id, subject_slug), None
    except ApiError as exc:
        return [], exc.message


def _load_messages(chat_id: str | None) -> tuple[list[dict], str | None]:
    if not chat_id:
        return [], None
    try:
        return api_client.get_chat_messages(chat_id), None
    except ApiError as exc:
        return [], exc.message
