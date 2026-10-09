import os
from dotenv import load_dotenv
import chromadb
from llama_index.core.node_parser import HierarchicalNodeParser, get_leaf_nodes
from llama_index.core import VectorStoreIndex, StorageContext
from llama_index.core.retrievers import AutoMergingRetriever
from llama_index.core.storage.docstore import SimpleDocumentStore
from llama_index.embeddings.fastembed import FastEmbedEmbedding

from ingestion.storage import Storage


embed_model = FastEmbedEmbedding(
    model_name="BAAI/bge-small-en-v1.5",
    cache_dir="./models",  # see the note below
)

storage = Storage()

class Chunk:
    def __init__(self):
        pass
    def chunk_documents(self, docs):
        redis_docstore = storage.redis()
        vector_store = storage.chroma()
        
        storage_context = StorageContext.from_defaults(
            docstore=redis_docstore,
            vector_store=vector_store,
            )


        # 1. Create a true hierarchical parser
        # Slices documents into 2048 tokens, then 512 tokens, then 128 tokens
        node_parser = HierarchicalNodeParser.from_defaults(
            chunk_sizes=[2048, 512, 128]
        )

        # 2. Parse the documents and isolate the smallest chunks (leaves)
        nodes = node_parser.get_nodes_from_documents(docs)
        leaf_nodes = get_leaf_nodes(nodes) 

        
        redis_docstore.add_documents(nodes)
       

        # 4. Build the vector index strictly using the smallest 128-token leaf nodes
        base_index = VectorStoreIndex(
            leaf_nodes, storage_context=storage_context, embed_model=embed_model
        )
        base_retriever = base_index.as_retriever(similarity_top_k=6)

        # 5. Initialize the Auto-Merging Retriever
        # If 3 or more of the retrieved 128-token chunks belong to the same 512-token 
        # parent chunk, it automatically drops the children and returns the parent.
        retriever = AutoMergingRetriever(
            base_retriever, 
            storage_context, 
            verbose=True
        )

        return retriever


