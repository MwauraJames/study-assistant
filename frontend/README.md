# Study Assistant frontend

Streamlit UI for the Study Assistant API. Accounts, subjects, and the document list live in a local SQLite database. The backend only receives `user_id` (the account UUID) and `subject` (the subject slug).

## Setup

From this `frontend/` directory, with Python 3.11+ and [uv](https://docs.astral.sh/uv/):

```bash
uv sync
cp .env.example .env
```

`API_URL` defaults to `http://localhost:8000`. `DB_PATH` defaults to `./data/app.db` (the `data/` folder is created automatically).

## Run with the fake backend

The fake backend implements `/upload`, `/status/{doc_id}`, `/ask`, `/chats/{user_id}`, and `/chats/{chat_id}/messages` so you can develop without LlamaCloud, Qdrant, or API keys. Files become `ready` after about five seconds. A filename containing `fail` ends as `failed`. Answers include a citation marker so the UI can strip it. Follow-up questions reuse the returned `chat_id` so the conversation stays continuous.

```bash
uv run uvicorn tests.fake_backend:app --port 8000
```

In another terminal:

```bash
uv run streamlit run app.py
```

## Run with the real backend

Start the FastAPI app from the repository root so it listens on port 8000 (or set `API_URL` in `frontend/.env`). Then:

```bash
uv run streamlit run app.py
```

## Tests

```bash
uv run pytest
```

## Known limits (v1)

- A browser refresh logs you out. Session state is not persisted.
- Chat is a continuous conversation: the UI sends `chat_id` on `/ask` and loads history from the backend. A browser refresh still logs you out, so you pick the thread up again from the conversation list after logging in.
- There is no delete, share, password reset, or document preview.
- Status is polled from the backend; if the server restarts, in-flight documents become `unknown` and may need to be uploaded again.
- **This login protects the UI only.** The backend trusts the `user_id` it receives. Do not expose the backend on the public internet until it has real authentication.
