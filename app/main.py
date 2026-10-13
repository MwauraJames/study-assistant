import os
import shutil
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
from ingestion.reset_store import reset_redis, reset_chroma
from retrieval.reranker import rerank_documents
from retrieval.expand import expand_query
from retrieval.hybrid_search import (
    build_hybrid_retriever, hybrid_search, expand_to_parents
)
from generation.llm import generate_response
from generation.response import final_response


# ---------- Setup ----------
app = FastAPI()

storage = Storage()
embed_model = Embed().get_embedding()
client = LlamaCloud()

reset_redis(storage)
reset_chroma(storage)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Tracks the one document: "empty" -> "processing" -> "ready" / "failed"
state = {"status": "empty", "error": None}


class Question(BaseModel):
    query: str


# ---------- Pipelines ----------
@traceable(name="ingest_pipeline", run_type="chain")
def ingest_pipeline(file_path):
    try:
        state["status"] = "processing"
        parsed_content = parse_document(client, file_path)
        chunk_documents(storage, embed_model, [Document(text=parsed_content)])
        state["status"] = "ready"
    except Exception as e:
        state["status"] = "failed"
        state["error"] = str(e)
        raise


@traceable(name="retrieval_pipeline", run_type="chain")
def retrieval_pipeline(query):
    expanded_query = expand_query(generate_response, query)

    hybrid_retriever = build_hybrid_retriever(storage, embed_model)
    fused_results = hybrid_retriever.retrieve(expanded_query)

    parent_store = storage.redis("university_app_docs")
    parent_nodes = expand_to_parents(fused_results, parent_store)

    texts = [p.node.get_content() for p in parent_nodes]
    reranked_results = rerank_documents(query, texts, "rerank-v4.0-pro", top_n=1)

    best = reranked_results.results[0]
    best_node = parent_nodes[best.index].node
    return best_node.get_content()


@traceable(name="response_pipeline", run_type="chain")
def response_pipeline(query):
    best_text = retrieval_pipeline(query)
    full_message = f"Query: {query}\nSource Documents:\n{best_text}"
    return final_response(generate_response, full_message)


# ---------- Endpoints ----------
@app.post("/upload", status_code=202)
def upload_file(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    file_path = UPLOAD_DIR / file.filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    state["status"] = "processing"
    state["error"] = None
    background_tasks.add_task(ingest_pipeline, str(file_path))
    return {"filepath": str(file_path), "status": state["status"]}


@app.get("/status")
def get_status():
    return state


@app.post("/ask")
def ask(body: Question):
    if state["status"] != "ready":
        raise HTTPException(
            status_code=409,
            detail=f"Document not ready (status: {state['status']}). Upload one and wait for 'ready'.",
        )
    return {"answer": response_pipeline(body.query)}