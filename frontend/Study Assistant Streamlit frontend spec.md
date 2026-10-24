# Study Assistant: Streamlit frontend (build spec for Cursor)

*Prepared for James Mwaura · October 22, 2026. Give this file to Cursor as the single source of truth and build in the order of section 12.*

## 1. What to build

A Streamlit app that talks to the existing FastAPI backend. A user can:

1. Create an account and log in.
2. Create subjects (for example Physics, Chemistry). A subject is a private folder of study material.
3. Upload documents into one subject and watch each one finish processing.
4. Open a subject and chat. Every answer must come only from that subject's documents, never from another subject's.

Keep it simple, clean and quick to build. No streaming, no admin panel, no sharing.

## 2. Backend contract (exists today; the frontend must not change it)

Base URL comes from `API_URL` (default `http://localhost:8000`). The backend is `main.py` with these endpoints:

- `POST /upload` (multipart form): fields `file`, `user_id`, `subject` (all required) and `doc_id` (optional). Returns 202 with `{doc_id, user_id, subject, status}`. Processing runs in the background and can take seconds to minutes.
- `GET /status/{doc_id}`: returns `{doc_id, status, error}` where status is `processing`, `ready` or `failed`. Returns 404 for an unknown `doc_id`. Status is kept in server memory, so it is lost when the server restarts.
- `POST /ask` (JSON): `{query, user_id, subject?, doc_id?}`. Returns `{answer}`. Returns 409 if the given `doc_id` is still processing. A request takes several seconds (often 5 to 20). There is no streaming and no conversation memory: every question is answered on its own.
- `subject` is optional on `/ask`, so omitting it is expected to widen the search to all of that user's documents. The frontend must therefore send `subject` on every `/ask` call. This rule is what guarantees subject isolation.

Answers can contain citation markers such as 【source】 or 【1†L1-L3】. The frontend removes them before display.

## 3. What the backend does not have, and the workaround

The backend has no accounts, no subject list, no document list, no delete and no sources in answers. For v1 the frontend owns accounts, subjects and the document list in a local SQLite database, and the backend just receives strings.

- `user_id` sent to the backend is the account's immutable UUID, never the username.
- `subject` sent to the backend is the subject's immutable `slug`.
- The documents list is the frontend's own record, filled from the `doc_id` it generated and sent with `/upload`.
- Delete and sources are NOT in v1 (see sections 13 and 14). If `/ask` ever returns a `sources` list, show it under the answer; otherwise show nothing.
- The trust model is weak: the backend believes whatever `user_id` it is sent. That is acceptable only while the backend is not reachable from the public internet. Real authentication comes later.

## 4. Tech and project layout

Python 3.11 or newer, managed with `uv`. Dependencies: `streamlit` (recent, 1.40 or newer), `requests`, `bcrypt`, `python-dotenv`. Dev dependencies: `pytest`, `fastapi`, `uvicorn` (for the fake backend).

```
frontend/
  app.py                  entrypoint: page config, session setup, auth gate, layout
  core/config.py          settings from environment
  core/db.py              sqlite3 connection, schema creation, queries
  core/auth.py            validation, bcrypt hashing, login lockout
  core/api_client.py      the only module that talks HTTP to the backend
  core/text_utils.py      slugify, clean_answer, filename and size helpers
  ui/auth_ui.py           login and sign-up forms
  ui/sidebar.py           user box, subject list, new-subject dialog, backend status
  ui/documents_ui.py      upload form, document table, status polling
  ui/chat_ui.py           chat for the selected subject
  tests/                  unit tests and fake_backend.py
  .streamlit/config.toml  upload size limit, theme
  .env.example, README.md, pyproject.toml
```

UI modules never call `requests` or `sqlite3` directly; they use `api_client` and `db`.

## 5. Data model (SQLite at `DB_PATH`)

Turn on foreign keys and WAL mode. Use parameterized queries only. Create the tables on startup if they are missing.

- `users`: `id` (UUID text, primary key), `username` (unique, case-insensitive), `display_name`, `password_hash`, `created_at`, `failed_logins`, `locked_until`.
- `subjects`: `id` (UUID), `user_id` (foreign key), `slug`, `name`, `created_at`. Unique on (`user_id`, `slug`).
- `documents`: `id` (this is the backend `doc_id`, a UUID), `user_id`, `subject_id`, `filename`, `size_bytes`, `sha256`, `status` (`uploading`, `processing`, `ready`, `failed`, `unknown`), `error`, `created_at`, `updated_at`.
- `messages`: `id` (integer), `user_id`, `subject_id`, `doc_id` (nullable, the document scope used), `role` (`user` or `assistant`), `content` (raw text as returned), `created_at`.

Every query that returns subjects, documents or messages must filter by the logged-in user's `id`.

## 6. Screens and behavior

### 6.1 Login and sign-up

- Logged-out users see only a centered card with two tabs: Log in and Sign up.
- Sign up: username (3 to 32 characters: letters, digits, underscore), optional display name, password and confirm password (at least 8 characters). Reject a taken username with a clear message. On success, log the user in.
- Log in: username and password. On any failure show the same message ('Wrong username or password'). After 5 failed attempts lock the account for 5 minutes.
- Hash with bcrypt. Never store, log or display a password.
- The session lives in `st.session_state` (`user`: id, username, display name). A browser refresh logs the user out in v1; that is accepted and noted in the README.
- Log out clears the whole session state, including the selected subject and any cached data.

### 6.2 App shell

- Page title 'Study Assistant', wide layout.
- Sidebar: greeting with the display name, Log out button, a backend connection indicator (green when reachable, red with a retry button; use a short cached request), then the subject list and a New subject button.
- Subject list: one button or radio item per subject, showing its count of ready documents. The selected subject is stored in `st.session_state['subject_id']` and highlighted.
- Main area for the selected subject: a header with the subject name, then two tabs: Chat and Documents.
- Empty state when the user has no subjects: a friendly message and a New subject button, no tabs.

### 6.3 Subjects

- New subject opens a dialog: name (1 to 60 characters). The slug is generated from the name (lowercase, letters and digits, hyphens) and shown as a preview. If the slug already exists for this user, show an error and do not create it.
- The slug never changes after creation, because the backend stores documents under it. The display name can be edited (a small Rename action).
- No delete in v1.

### 6.4 Documents tab

- Upload form: `st.file_uploader` allowing multiple files. Accepted types: pdf, docx, pptx, txt, md. Size limit from `MAX_UPLOAD_MB` (default 25), also set in `.streamlit/config.toml`.
- A Process button uploads the files one at a time. For each file: compute SHA-256; if a document with the same hash already exists in this subject, warn and skip it unless the user ticks 'Upload anyway'. Generate a UUID `doc_id` in the frontend, insert the row with status `uploading`, call `POST /upload` with `user_id`, the subject slug and that `doc_id`, then set the status to `processing`. If the request fails, set `failed` with the error text.
- Documents table for the current subject (newest first): filename, size, status badge (processing, ready, failed, unknown), uploaded time, and the error text for failures.
- Polling: while any document in the subject is `processing`, a fragment (`st.fragment(run_every='3s')`) calls `GET /status/{doc_id}` for each one and updates the database. Stop polling when none are processing. If a status call returns 404 (server restarted), set the document to `unknown` and explain in a tooltip that it may need to be uploaded again. If a document stays `processing` for more than 15 minutes, show 'taking unusually long'.
- A failed document shows its error; the user re-selects the file and uploads again (the app does not keep file bytes).

### 6.5 Chat tab

- Header: 'Chatting with: \<subject name>'. Caption: 'Answers use only the documents in this subject. Each question is answered on its own, with no memory of earlier messages.'
- Scope selector in an expander: 'All documents in this subject' (default) or one specific ready document. A specific choice sends its `doc_id`.
- The chat input is disabled, with an explanation, when the subject has no `ready` document. If some documents are still processing, say so.
- On submit: save the user message, show it, call `POST /ask` with `query`, `user_id`, the subject slug and the optional `doc_id`, with a spinner ('Searching your documents...'). Show the answer, then save it. On failure show a short error message in the chat (not a stack trace) and keep the user's text so they can retry.
- Display answers through `clean_answer()`, which removes citation markers (anything between 【 and 】) and trims whitespace. Store the raw answer in the database. Render as Markdown with unsafe HTML disabled.
- Chat history is per user and per subject, loaded from `messages` when the tab opens, newest at the bottom. Switching subjects shows that subject's history and never mixes them. A Clear chat button deletes only this subject's messages (frontend only).
- Maximum question length is 2000 characters.
- If the response contains `sources`, show them in an expander under the answer. Otherwise show nothing.

## 7. API client rules

- One module, `core/api_client.py`, with `upload(...)`, `get_status(...)`, `ask(...)` and `ping()`. Return small dataclasses, not raw responses. Use one `requests.Session`.
- Timeouts: connect 5 s; read 120 s for `/ask` and `/upload`; 10 s for status and ping.
- Map failures to friendly messages: cannot connect ('Cannot reach the server. Is the backend running?'), timeout ('This is taking too long. Try again.'), 404 on status (unknown document), 409 on ask ('That document is still processing.'), 422 ('The server rejected the request.'), 5xx ('Something went wrong on the server.'). Log technical details to the console, never passwords or document text.
- No retries on `/upload` (it is not idempotent). One retry on connection errors for `/status` and `ping` only.
- Never send a `user_id` or `subject` taken from text the user typed. They come from the session and the database.

## 8. Security and privacy

- Parameterized SQL only. bcrypt for passwords. No secrets in code; read the backend URL and settings from environment variables or `.env`.
- Every database read and write is scoped by the logged-in `user_id`. A user must never be able to see another user's subjects, documents or messages, even by editing the session or the URL.
- Do not enable `unsafe_allow_html` anywhere that renders answers or filenames.
- Do not log document contents, questions or answers at INFO level.
- Put this caveat in the README: this login protects the UI only, because the backend trusts the `user_id` it receives. Do not expose the backend publicly until it has real authentication.

## 9. Configuration

Environment variables, with a `.env.example`: `API_URL` (default `http://localhost:8000`), `DB_PATH` (default `./data/app.db`), `MAX_UPLOAD_MB` (25), `ASK_TIMEOUT_S` (120), `UPLOAD_TIMEOUT_S` (120), `POLL_SECONDS` (3), `ENABLE_DELETE` (false). Create the `data/` folder automatically. Add `data/` and `.env` to `.gitignore`.

## 10. Fake backend and tests

So the frontend can be built and tested without LlamaCloud, Qdrant or API keys, write `tests/fake_backend.py`, a tiny FastAPI app that mimics the contract in section 2:

- `POST /upload` accepts the same form fields, answers 202, and marks the document `ready` after about 5 seconds (any file with `fail` in its name ends as `failed`).
- `GET /status/{doc_id}` returns the status, or 404 for unknown ids.
- `POST /ask` waits 2 seconds and returns an answer that mentions the subject and contains a citation marker such as 【source】, so the cleaning code is exercised. It returns 409 if the given `doc_id` is still processing.
- It stores `user_id` and `subject` per document, and `/ask` answers 'nothing found' for a subject with no documents, so subject isolation can be checked.

Run it with `uvicorn tests.fake_backend:app --port 8000`. Tests (pytest): slugify, `clean_answer`, password hashing and lockout, subject uniqueness, per-user scoping in every query, the API client's error mapping (mock `requests`), and a Streamlit `AppTest` flow: sign up, create a subject, upload (mocked), chat (mocked), switch subject and confirm the histories are separate.

## 11. Acceptance criteria

1. A new user can sign up, log out and log back in. Wrong credentials give one generic error; 5 failures lock the account for 5 minutes.
2. Two users cannot see each other's subjects, documents or chat history.
3. A user can create a subject, and creating the same name twice is rejected.
4. Uploading three files shows three rows that move from processing to ready (or failed with a message) without the user reloading the page.
5. Uploading the same file twice into one subject warns before sending it again.
6. In subject A, a question is sent to `/ask` with subject A's slug and the user's id; the same question in subject B uses B's slug. `/ask` is never called without a subject.
7. Chat is disabled with an explanation when a subject has no ready document.
8. Answers show no 【...】 markers. Chat history survives switching subjects and coming back (but not a browser refresh, which logs the user out).
9. With the backend stopped, every screen shows a friendly connection error, not a traceback, and recovers when the backend returns.
10. No password or document text appears in the logs.

## 12. Build order for Cursor

1. Project skeleton, config, database schema, `text_utils`, and their tests.
2. Auth (sign up, log in, log out, lockout) with its tests.
3. Fake backend and the API client with error mapping.
4. App shell: sidebar, subjects, New subject dialog.
5. Documents tab: upload and status polling.
6. Chat tab.
7. README (setup with `uv`, how to run the fake backend and the real one, known limits) and a final pass against section 11.

After each step, run the tests and tell me what changed and why, in plain language.

## 13. Not in v1

Streaming answers, conversation memory, searching across subjects, document preview, deleting documents or subjects, sharing, password reset, email verification, social login, persistent login across a refresh, deployment setup. These can be added once the backend supports them.

## 14. Backend work this frontend depends on (separate from the frontend)

Needed for the next version:

- `GET /documents?user_id=...` and persistent document status, so statuses survive a server restart and the frontend does not have to remember everything.
- `DELETE /documents/{doc_id}` scoped to the owner, then turn on `ENABLE_DELETE`.
- `sources` (filenames) in the `/ask` response.
- A `/health` endpoint for the connection indicator.
- Real authentication (for example JWT) replacing the client-sent `user_id`, with accounts and subjects stored by the backend.

## 15. Problems spotted in the current `main.py` (fix before exposing the API)

1. Path traversal: the upload path is built from the client-supplied `doc_id` (`f'{doc_id}_{filename}'`). A `doc_id` containing `../` can write outside the uploads folder. Accept only UUID-shaped ids, or ignore the client's `doc_id` and always generate it on the server.
2. Cross-user deletion: re-uploading with an existing `doc_id` calls `delete_by_doc_id(storage, doc_id)` without checking the owner, so one user could delete another user's points by guessing or reusing an id. Scope the deletion by `user_id` and `doc_id` together.
3. `/status/{doc_id}` and `/ask` trust any `user_id`; until authentication exists, keep the backend off the public internet.
4. `/ask` without `subject` searches beyond a single subject. That is fine as a feature, but today only the frontend's rule keeps subjects isolated.
5. `doc_statuses` is a per-process dictionary: it resets on restart and is not shared between workers.
