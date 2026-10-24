import shutil
import uuid
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, File, Form, UploadFile, BackgroundTasks, HTTPException
from pydantic import BaseModel

from llama_index.core import Document
from llama_cloud import LlamaCloud
from langsmith import traceable

from ingestion.parse import parse_document
from ingestion.chunk import chunk_documents
from ingestion.storage import Storage
from ingestion.embed import Embed
from ingestion.reset_store import delete_by_doc_id
from retrieval.reranker import rerank_documents
from retrieval.expand import expand_query
from generation.response import final_response
from models import model
from retrieval.hybrid_search import build_hybrid_retriever, merge_leaves_to_parents
from config import Settings


# ---------- Setup ----------
app = FastAPI()

settings = Settings()
storage = Storage()
embed_model = Embed().get_embedding()
client = LlamaCloud()

UPLOAD_DIR = Path(settings.upload_dir)
UPLOAD_DIR.mkdir(exist_ok=True)

# Track ingestion status per doc_id instead of blocking the entire server
doc_statuses: dict[str, dict] = {}


class Question(BaseModel):
    query: str
    user_id: str
    subject: Optional[str] = None
    doc_id: Optional[str] = None


# ---------- Pipelines ----------
@traceable(name="ingest_pipeline", run_type="chain")
def ingest_pipeline(file_path: str, user_id: str, subject: str, doc_id: str):
    try:
        parsed_content = parse_document(client, file_path)

        # If re-uploading the same doc_id, clear only its old points first
        delete_by_doc_id(storage, doc_id)

        chunk_documents(
            storage=storage,
            embed_model=embed_model,
            docs=[Document(text=parsed_content)],
            user_id=user_id,
            subject=subject,
            doc_id=doc_id,
        )
        doc_statuses[doc_id] = {"status": "ready", "error": None}
    except Exception as e:
        doc_statuses[doc_id] = {"status": "failed", "error": str(e)}
        try:
            delete_by_doc_id(storage, doc_id)  # Clean up partial writes for this doc_id
        except Exception:
            pass
        raise


@traceable(name="retrieval_pipeline", run_type="chain")
def retrieval_pipeline(
    query: str,
    user_id: str,
    subject: Optional[str] = None,
    doc_id: Optional[str] = None,
) -> str:
    # 1. Expand the question
    expanded_query = expand_query(model, query)

    # 2. Build filtered Qdrant hybrid retriever and retrieve top-k 128-token leaves
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

    # 3. Promote leaves to their unique 512-token parent texts from Qdrant payload
    candidate_texts = merge_leaves_to_parents(leaf_results)
    if not candidate_texts:
        return "" 

    # 4. Rerank unique parent blocks against the original question
    reranked = rerank_documents(query, candidate_texts)
    best = [candidate_texts[r.index] for r in reranked.results]

    return "\n\n---\n\n".join(best)


@traceable(name="response_pipeline", run_type="chain")
def response_pipeline(body: Question) -> str:
    context = retrieval_pipeline(
        query=body.query,
        user_id=body.user_id,
        subject=body.subject,
        doc_id=body.doc_id,
    )
    if not context:
        return "I couldn't find anything relevant to that in your documents."
    full_message = f"Query: {body.query}\nSource Documents:\n{context}"
    return final_response(model, full_message)


# ---------- Endpoints ----------
@app.post("/upload", status_code=202)
def upload_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str = Form(...),
    subject: str = Form(...),
    doc_id: Optional[str] = Form(None),
):
    doc_id = doc_id or str(uuid.uuid4())
    doc_statuses[doc_id] = {"status": "processing", "error": None}

    try:
        safe_name = f"{doc_id}_{Path(file.filename).name}"
        file_path = UPLOAD_DIR / safe_name
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        doc_statuses[doc_id] = {"status": "failed", "error": str(e)}
        raise HTTPException(500, f"Could not save the upload: {e}")

    background_tasks.add_task(
        ingest_pipeline, str(file_path), user_id, subject, doc_id
    )
    return {
        "doc_id": doc_id,
        "user_id": user_id,
        "subject": subject,
        "status": doc_statuses[doc_id]["status"],
    }


@app.get("/status/{doc_id}")
def get_status(doc_id: str):
    if doc_id not in doc_statuses:
        raise HTTPException(404, f"Unknown doc_id: {doc_id}")
    return {"doc_id": doc_id, **doc_statuses[doc_id]}


@app.post("/ask")
def ask(body: Question):
    if body.doc_id and doc_statuses.get(body.doc_id, {}).get("status") == "processing":
        raise HTTPException(
            status_code=409,
            detail=f"Document {body.doc_id} is still processing.",
        )
    return {"answer": response_pipeline(body)}