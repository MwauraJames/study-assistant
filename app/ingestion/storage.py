# ingestion/storage.py
import chromadb

from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.storage.docstore.redis import RedisDocumentStore

from config import Settings

settings = Settings()

# One place for every name/path, so ingestion, retrieval and reset can never disagree.
CHROMA_PATH = settings.chroma_path
CHROMA_COLLECTION = settings.chroma_collection
BM25_DIR = settings.bm25_dir
REDIS_NAMESPACE = settings.redis_namespace


class Storage:
    def __init__(self):
        # ONE Chroma client for the whole process (before, a new PersistentClient
        # was created on every call to chroma()).
        self.chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
        self._redis_stores = {}

    def chroma_collection(self):
        return self.chroma_client.get_or_create_collection(CHROMA_COLLECTION)

    def chroma(self):
        # Always wrap a fresh get_or_create, so after a reset you never hold a
        # wrapper pointing at a deleted collection.
        return ChromaVectorStore(chroma_collection=self.chroma_collection())

    def redis(self, namespace: str = REDIS_NAMESPACE):
        if namespace not in self._redis_stores:
            self._redis_stores[namespace] = RedisDocumentStore.from_host_and_port(
                host="127.0.0.1", port=6379, namespace=namespace
            )
        return self._redis_stores[namespace]