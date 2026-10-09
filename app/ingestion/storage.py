import chromadb
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.storage.docstore.redis import RedisDocumentStore

class Storage:
    def chroma(self):
        chroma_client = chromadb.PersistentClient(path="./chroma_db_storage")
        chroma_collection = chroma_client.get_or_create_collection("university_nodes")
        return ChromaVectorStore(chroma_collection=chroma_collection)

    def redis(self):
        # -- Set up Redis for Document Storage (Large Parent Chunks) --
        return RedisDocumentStore.from_host_and_port(
            host="127.0.0.1", 
            port=6379, 
            namespace="university_app_docs"
        )