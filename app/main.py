import os
from dotenv import load_dotenv
load_dotenv()
from llama_index.core import Document
from ingestion.parse import parse_document
from ingestion.chunk import chunk_documents
from llama_cloud import LlamaCloud
#from observability.langfuse import attach_langfuse_observability
from ingestion.storage import Storage
from generation.response import final_response
from langsmith.wrappers import wrap_openai
from langsmith import traceable
from ingestion.embed import Embed   
from langfuse import observe
from retrieval.reranker import rerank_documents
from retrieval.expand import expand_query
from generation.llm import generate_response
from retrieval.hybrid_search import (
    build_hybrid_retriever, hybrid_search, expand_to_parents
)
from langsmith import Client
from ingestion.reset_store import reset_redis, reset_chroma     

  # Load environment variables from .env file


storage = Storage()
embed_model = Embed().get_embedding()

reset_redis(storage)
reset_chroma(storage)

file_path = "test.txt"  # Replace with the path to your document
query = "What technique was used for non-volatile read-only storage and who manufactured it?"  # Replace with your query


#Ingestion Pipeline: Parse -> Chunk -> Store
api_key = os.getenv("LLAMA_CLOUD_API_KEY")

client = LlamaCloud()

def ingest_pipeline(file_path):
            #Parse
    parsed_content = parse_document(client, file_path)
            #Chunk and Store
    chunked_stored_content= chunk_documents(storage, embed_model, [Document(text=parsed_content)])



def retrieval_pipeline(query):
            #Expand query
    expanded_query = expand_query(generate_response, query)

            #Hybrid Search
    hybrid_retriever = build_hybrid_retriever(storage, embed_model)
    fused_results = hybrid_retriever.retrieve(expanded_query)
    
    parent_store = storage.redis("university_app_docs")
    parent_nodes = expand_to_parents(fused_results, parent_store)

    texts = [p.node.get_content() for p in parent_nodes]

    reranked_results = rerank_documents(query, texts, "rerank-v4.0-pro", top_n=1)

    best = reranked_results.results[0]            # highest-scoring hit
    best_node = parent_nodes[best.index].node     # full parent chunk (TextNode)
    best_text = best_node.get_content()           # text to give the LLM
    best_score = best.relevance_score     
    
    return best_text        

    

def response_pipeline(query):
        best_text = retrieval_pipeline(query)
        full_message = f"Query: {query}\n\ Source Documents:\n{best_text}"
        response = final_response(generate_response, full_message)

        print("Final Response:\n", response)
        return response

@traceable(name="full_run", run_type="chain")
def full_run():
        ingest_pipeline(file_path)
        response_pipeline(query)

full_run()

Client().flush()


                

                

            







