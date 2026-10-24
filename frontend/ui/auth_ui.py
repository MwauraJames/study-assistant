from __future__ import annotations

import streamlit as st

from core.auth import AuthError, login, signup


def render_auth() -> None:
    left, card, right = st.columns([1, 2, 1])
    with card:
        st.title("Study Assistant")
        st.caption("Sign in to your private study folders.")
        login_tab, signup_tab = st.tabs(["Log in", "Sign up"])
        with login_tab:
            _login_form()
        with signup_tab:
            _signup_form()


def _login_form() -> None:
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in", use_container_width=True)
    if submitted:
        try:
            st.session_state["user"] = login(username, password)
            st.rerun()
        except AuthError as exc:
            st.error(exc.message)


def _signup_form() -> None:
    with st.form("signup_form"):
        username = st.text_input("Username", help="3–32 characters: letters, digits, underscore.")
        display_name = st.text_input("Display name (optional)")
        password = st.text_input("Password", type="password")
        confirm = st.text_input("Confirm password", type="password")
        submitted = st.form_submit_button("Create account", use_container_width=True)
    if submitted:
        try:
            st.session_state["user"] = signup(username, password, confirm, display_name)
            st.rerun()
        except AuthError as exc:
            st.error(exc.message)
