from __future__ import annotations

import streamlit as st

from core import api_client, db
from core.text_utils import slugify

NAME_MIN, NAME_MAX = 1, 60


def logout() -> None:
    st.session_state.clear()
    st.rerun()


@st.cache_data(ttl=5, show_spinner=False)
def _cached_ping() -> bool:
    return api_client.ping()


def render_sidebar(user: dict) -> None:
    with st.sidebar:
        display = user.get("display_name") or user["username"]
        st.subheader(f"Hello, {display}")
        if st.button("Log out", use_container_width=True):
            logout()

        reachable = _cached_ping()
        status_col, retry_col = st.columns([3, 1])
        with status_col:
            if reachable:
                st.markdown("Backend: :green[connected]")
            else:
                st.markdown("Backend: :red[unreachable]")
        with retry_col:
            if st.button("Retry", use_container_width=True):
                _cached_ping.clear()
                st.rerun()

        st.divider()
        st.markdown("**Subjects**")
        subjects = db.list_subjects(user["id"])
        selected = st.session_state.get("subject_id")
        if selected and not any(s["id"] == selected for s in subjects):
            st.session_state["subject_id"] = None
            selected = None

        if not subjects:
            st.caption("No subjects yet.")
        else:
            options = [s["id"] for s in subjects]
            labels = {
                s["id"]: f"{s['name']} ({s['ready_count']} ready)" for s in subjects
            }
            current = selected if selected in options else options[0]
            chosen = st.radio(
                "Subject list",
                options,
                index=options.index(current),
                format_func=lambda sid: labels[sid],
                label_visibility="collapsed",
                key="subject_radio",
            )
            st.session_state["subject_id"] = chosen

        if st.button("New subject", use_container_width=True):
            st.session_state["show_new_subject"] = True

        if st.session_state.get("show_new_subject"):
            new_subject_dialog(user["id"])


@st.dialog("New subject")
def new_subject_dialog(user_id: str) -> None:
    name = st.text_input("Name", max_chars=NAME_MAX, key="new_subject_name")
    slug = slugify(name)
    st.caption(f"Slug preview: `{slug or '—'}` (this cannot change later)")
    col_ok, col_cancel = st.columns(2)
    with col_ok:
        create = st.button("Create", type="primary", use_container_width=True)
    with col_cancel:
        cancel = st.button("Cancel", use_container_width=True)
    if cancel:
        st.session_state["show_new_subject"] = False
        st.rerun()
    if create:
        _create_subject(user_id, name, slug)


def _create_subject(user_id: str, name: str, slug: str) -> None:
    name = (name or "").strip()
    if len(name) < NAME_MIN or len(name) > NAME_MAX:
        st.error("Name must be 1 to 60 characters.")
        return
    if not slug:
        st.error("That name does not produce a usable slug.")
        return
    if db.subject_slug_exists(user_id, slug):
        st.error("You already have a subject with this name.")
        return
    try:
        subject = db.create_subject(user_id, name, slug)
    except Exception:
        st.error("You already have a subject with this name.")
        return
    st.session_state["subject_id"] = subject["id"]
    st.session_state["show_new_subject"] = False
    st.rerun()


@st.dialog("Rename subject")
def rename_subject_dialog(user_id: str, subject: dict) -> None:
    name = st.text_input(
        "Display name",
        value=subject["name"],
        max_chars=NAME_MAX,
        key="rename_subject_name",
    )
    st.caption(f"Slug stays `{subject['slug']}`.")
    if st.button("Save", type="primary"):
        name = (name or "").strip()
        if len(name) < NAME_MIN or len(name) > NAME_MAX:
            st.error("Name must be 1 to 60 characters.")
            return
        db.rename_subject(user_id, subject["id"], name)
        st.session_state["show_rename"] = False
        st.rerun()


def prompt_rename() -> None:
    st.session_state["show_rename"] = True
