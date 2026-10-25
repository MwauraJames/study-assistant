import uuid
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, File, Form, UploadFile, BackgroundTasks, HTTPException
from pydantic import BaseModel

from llama_index.core import Document
from langsmith import traceable
from llama_cloud import LlamaCloud

from ingestion.parse import parse_document
from ingestion.chunk import chunk_documents
from ingestion.storage import Storage
from ingestion.mongo_store import MongoStore
from ingestion.embed import Embed
from ingestion.reset_store import delete_by_doc_id, reset_all
from retrieval.reranker import rerank_documents
from retrieval.expand import expand_query
from retrieval.hybrid_search import build_hybrid_retriever, merge_leaves_to_parents
from generation.response import final_response
from models import model
from config import Settings


# ---------- Setup ----------
app = FastAPI()

settings = Settings()
storage = Storage()          # Qdrant (Vectors + Hybrid Search)
mongo = MongoStore()         # MongoDB (Raw PDFs, Parsed Docs, Chat History)
embed_model = Embed().get_embedding()
client = LlamaCloud()


class Question(BaseModel):
    query: str
    user_id: str
    subject: Optional[str] = None
    doc_id: Optional[str] = None
    chat_id: Optional[str] = None  # Pass existing chat_id to continue a conversation


def format_history(messages: list[dict]) -> str:
    """Format MongoDB message records into a clean transcript for the LLM."""
    if not messages:
        return "No prior conversation."
    return "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in messages
    )


# ---------- Pipelines ----------
@traceable(name="ingest_pipeline", run_type="chain")
def ingest_pipeline(file_path: str, user_id: str, subject: str, doc_id: str):
    try:
        # 1. Parse PDF into Markdown locally
        parsed_content = parse_document(client , file_path)

        # 2. Clear any old Qdrant points for this doc_id and index new chunks
        delete_by_doc_id(storage, doc_id)
        stats = chunk_documents(
            storage=storage,
            embed_model=embed_model,
            docs=[Document(text=parsed_content)],
            user_id=user_id,
            subject=subject,
            doc_id=doc_id,
        )

        # 3. Persist the full parsed Markdown and 'ready' status in MongoDB
        mongo.save_parsed_document(
            doc_id=doc_id,
            parsed_markdown=parsed_content,
            num_leaves=stats["leaves"],
        )
    except Exception as e:
        mongo.mark_document_failed(doc_id, str(e))
        try:
            delete_by_doc_id(storage, doc_id)
        except Exception:
            pass
        raise


@traceable(name="retrieval_pipeline", run_type="chain")
def retrieval_pipeline(
    query: str,
    chat_history: list[dict],
    user_id: str,
    subject: Optional[str] = None,
    doc_id: Optional[str] = None,
) -> str:
    # 1. Contextualize + expand the query using recent chat history
    expanded_query = expand_query(model, query, chat_history=chat_history)

    # 2. Retrieve top-k 128-token leaves from Qdrant (dense + sparse RRF)
    retriever = build_hybrid_retriever(
        storage=storage,
        embed_model=embed_model,
        user_id=user_id,
        subject=subject,
        doc_id=doc_id,
    )
    leaf_results = retriever.retrieve(expanded_query)
    if not leaf_results:
        return ""

    # 3. Auto-merge sibling leaves into 512-token parents when threshold is met
    candidate_texts = merge_leaves_to_parents(leaf_results)
    if not candidate_texts:
        return ""

    # 4. Rerank against the expanded/contextualized query so pronouns don't confuse the reranker!
    reranked = rerank_documents(expanded_query, candidate_texts)
    best = [candidate_texts[r.index] for r in reranked.results]

    return "\n\n---\n\n".join(best)


@traceable(name="response_pipeline", run_type="chain")
def response_pipeline(body: Question, chat_id: str) -> str:
    # 1. Fetch past messages for this chat_id from MongoDB
    past_messages = mongo.get_recent_messages(chat_id)

    # 2. Retrieve relevant chunks from Qdrant
    context = retrieval_pipeline(
        query=body.query,
        chat_history=past_messages,
        user_id=body.user_id,
        subject=body.subject,
        doc_id=body.doc_id,
    )

    if not context:
        answer = "I couldn't find anything relevant to that in your documents."
    else:
        answer = final_response(
            model=model,
            query=body.query,
            context=context,
            chat_history=past_messages,
        )

    # 3. Save this turn (user question + assistant answer) in MongoDB
    mongo.add_message(chat_id, body.user_id, "user", body.query)
    mongo.add_message(chat_id, body.user_id, "assistant", answer)

    return answer


# ---------- Endpoints ----------
@app.post("/upload", status_code=202)
async def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str = Form(...),
    subject: str = Form(...),
    doc_id: Optional[str] = Form(None),  # frontend already posts this
):
    clean_name = Path(file.filename).name
    if not doc_id:
        doc_id = f"{user_id}_{subject}_{clean_name}"
    # ... create_document_record / ingest with this doc_id ...
    try:
        raw_bytes = await file.read()

        # 1. Store unprocessed binary in MongoDB GridFS + initialize status
        mongo.create_document_record(
            doc_id=doc_id,
            user_id=user_id,
            subject=subject,
            filename=clean_name,
            raw_bytes=raw_bytes,
            content_type=file.content_type or "application/pdf",
        )

    except Exception as e:
        raise HTTPException(500, f"Could not save upload: {e}")

    background_tasks.add_task(
        ingest_pipeline, str(file_path), user_id, subject, doc_id
    )
    return {
        "doc_id": doc_id,
        "user_id": user_id,
        "subject": subject,
        "status": "processing",
    }


@app.get("/status/{doc_id}")
def get_status(doc_id: str):
    record = mongo.get_document_status(doc_id)
    if not record:
        raise HTTPException(404, f"Unknown doc_id: {doc_id}")
    return record


@app.post("/ask")
def ask(body: Question):
    # Clean out Swagger UI default "string" placeholders if present
    doc_id = None if body.doc_id in (None, "", "string") else body.doc_id
    subject = None if body.subject in (None, "", "string") else body.subject
    chat_id = (
        str(uuid.uuid4())
        if body.chat_id in (None, "", "string")
        else body.chat_id
    )

    body.doc_id = doc_id
    body.subject = subject

    # Ensure the chat session exists in MongoDB
    mongo.ensure_chat_session(
        chat_id=chat_id,
        user_id=body.user_id,
        subject=subject,
        title=body.query[:60],
    )

    answer = response_pipeline(body, chat_id=chat_id)
    return {
        "chat_id": chat_id,
        "answer": answer,
    }


@app.get("/chats/{user_id}")
def get_user_chats(user_id: str, subject: Optional[str] = None):
    """List all chat sessions for a user (and optional subject)."""
    return {"chats": mongo.list_user_chats(user_id, subject)}


@app.get("/chats/{chat_id}/messages")
def get_chat_history(chat_id: str):
    """Retrieve the message history for a specific chat session."""
    return {"chat_id": chat_id, "messages": mongo.get_recent_messages(chat_id, limit=100)}