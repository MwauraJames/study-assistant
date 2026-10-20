import shutil
import threading
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, File, UploadFile, BackgroundTasks, HTTPException
from pydantic import BaseModel

from llama_index.core import Document
from llama_cloud import LlamaCloud
from langsmith import traceable

from ingestion.parse import parse_document
from ingestion.chunk import chunk_documents
from ingestion.storage import Storage
from ingestion.embed import Embed
from ingestion.reset_store import reset_all
from retrieval.reranker import rerank_documents
from retrieval.expand import expand_query
from retrieval.hybrid_search import build_hybrid_retriever, drop_covered_nodes
from generation.response import final_response
from models import model
from config import Settings



# ---------- Setup ----------
app = FastAPI()

settings = Settings()
storage = Storage()
embed_model = Embed().get_embedding()
client = LlamaCloud()

reset_all(storage) 
  # Redis + Chroma + BM25 together (the Chroma reset used to silently do nothing)
RERANK_TOP_N = settings.rerank_top_n

UPLOAD_DIR = Path(settings.upload_dir)
UPLOAD_DIR.mkdir(exist_ok=True)

# Tracks the one document: "empty" -> "processing" -> "ready" / "failed"
state = {"status": "empty", "error": None}
state_lock = threading.Lock()
holder = {"retriever": None}   # built once per ingestion, reused by every question


class Question(BaseModel):
    query: str


# ---------- Pipelines ----------
@traceable(name="ingest_pipeline", run_type="chain")
def ingest_pipeline(file_path):
    try:
        holder["retriever"] = None
        parsed_content = parse_document(client, file_path)

        # Only wipe the old document once the new one parsed successfully, then
        # write all three stores fresh so they always describe the SAME document.
        reset_all(storage)
        chunk_documents(storage, embed_model, [Document(text=parsed_content)])

        holder["retriever"] = build_hybrid_retriever(storage, embed_model)
        state["status"] = "ready"
    except Exception as e:
        state["status"] = "failed"
        state["error"] = str(e)
        holder["retriever"] = None
        try:
            reset_all(storage)   # don't leave half-written stores behind
        except Exception:
            pass
        raise


@traceable(name="retrieval_pipeline", run_type="chain")
def retrieval_pipeline(query):
    # 1. Expand the question (falls back to the original if the LLM fails)

    expanded_query = expand_query(model, query)

    # 2. Search 50 leaves (dense + BM25, RRF), then merge sibling leaves into parents
    merged = holder["retriever"].retrieve(expanded_query)

     # 3. Remove blocks that are already contained inside a bigger returned block
    candidates = drop_covered_nodes(merged, storage.redis())
    if not candidates:
        return ""          

    # 4. Rerank ALL candidates against the original question, keep the best few
    texts = [c.node.get_content() for c in merged]
    reranked = rerank_documents(query, texts)

    best = [texts[r.index] for r in reranked.results]
    return "\n\n---\n\n".join(best)


@traceable(name="response_pipeline", run_type="chain")
def response_pipeline(query):
    context = retrieval_pipeline(query)
    if not context:
        return "I couldn't find anything relevant to that in the uploaded document."
    full_message = f"Query: {query}\nSource Documents:\n{context}"
    return final_response(model,full_message)


# ---------- Endpoints ----------
@app.post("/upload", status_code=202)
def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    # One ingestion at a time: two at once would write into the same stores.
    with state_lock:
        if state["status"] == "processing":
            raise HTTPException(409, "A document is still processing. Wait for it to finish.")
        state["status"] = "processing"
        state["error"] = None

    try:
        # Path(...).name strips any directories a client might put in the filename
        file_path = UPLOAD_DIR / Path(file.filename).name
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        state["status"] = "failed"
        state["error"] = str(e)
        raise HTTPException(500, f"Could not save the upload: {e}")

    background_tasks.add_task(ingest_pipeline, str(file_path))
    return {"filepath": str(file_path), "status": state["status"]}


@app.get("/status")
def get_status():
    return state


@app.post("/ask")
def ask(body: Question):
    if state["status"] != "ready" or holder["retriever"] is None:
        raise HTTPException(
            status_code=409,
            detail=f"Document not ready (status: {state['status']}). Upload one and wait for 'ready'.",
        )
    return {"answer": response_pipeline(body.query)}