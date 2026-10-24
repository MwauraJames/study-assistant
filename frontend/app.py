from __future__ import annotations

import streamlit as st

from core import db
from ui.auth_ui import render_auth
from ui.chat_ui import render_chat
from ui.documents_ui import render_documents
from ui.sidebar import prompt_rename, render_sidebar, rename_subject_dialog

st.set_page_config(page_title="Study Assistant", layout="wide")
db.init_db()

if "user" not in st.session_state:
    st.session_state["user"] = None
if "subject_id" not in st.session_state:
    st.session_state["subject_id"] = None
if "show_new_subject" not in st.session_state:
    st.session_state["show_new_subject"] = False
if "show_rename" not in st.session_state:
    st.session_state["show_rename"] = False

user = st.session_state.get("user")
if not user:
    render_auth()
    st.stop()

render_sidebar(user)

subjects = db.list_subjects(user["id"])
subject_id = st.session_state.get("subject_id")
subject = db.get_subject(user["id"], subject_id) if subject_id else None

if not subjects or subject is None:
    st.title("Study Assistant")
    st.info("Create a subject to upload notes and start chatting. Each subject stays private to you.")
    if st.button("New subject", key="empty_new_subject"):
        st.session_state["show_new_subject"] = True
        st.rerun()
    st.stop()

header_left, header_right = st.columns([4, 1])
with header_left:
    st.title(subject["name"])
    st.caption(f"Slug: `{subject['slug']}`")
with header_right:
    if st.button("Rename"):
        prompt_rename()

if st.session_state.get("show_rename"):
    rename_subject_dialog(user["id"], subject)

chat_tab, docs_tab = st.tabs(["Chat", "Documents"])
with chat_tab:
    render_chat(user, subject)
with docs_tab:
    render_documents(user, subject)
