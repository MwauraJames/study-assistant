import os
from dotenv import load_dotenv
import chromadb
from langsmith import traceable
from llama_index.core.node_parser import HierarchicalNodeParser, get_leaf_nodes
from llama_index.core import VectorStoreIndex, StorageContext
from llama_index.core.retrievers import AutoMergingRetriever

@traceable
def chunk_documents(storage,embed_model,docs):
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
        parent_nodes = node_parser.get_nodes_from_documents(docs)
        leaf_nodes = get_leaf_nodes(parent_nodes) 

        leaves_docstore = storage.redis("university_app_leaves")
        leaves_docstore.add_documents(leaf_nodes)

        
        redis_docstore.add_documents(parent_nodes)
        
       

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


