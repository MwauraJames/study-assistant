# ingestion/reset_store.py
import shutil

from ingestion.storage import BM25_DIR, CHROMA_COLLECTION, REDIS_NAMESPACE

# The old design kept a second "leaves" docstore. It is gone now, but this
# clears whatever it left behind in Redis. Safe to delete from this tuple
# after the first run of the new code.
LEGACY_NAMESPACES = ("university_app_leaves",)


def reset_redis(storage):
    for ns in (REDIS_NAMESPACE, *LEGACY_NAMESPACES):
        store = storage.redis(ns)
        for doc_id in list(store.docs):  # list() so we don't mutate while iterating
            store.delete_document(doc_id, raise_error=False)


def reset_chroma(storage):
    # storage.chroma() returns a ChromaVectorStore, which has no delete_collection(),
    # so the old call raised AttributeError and the bare `except` hid it.
    # Use the real Chroma client, and no blanket except: a real error must be visible.
    existing = {getattr(c, "name", c) for c in storage.chroma_client.list_collections()}
    if CHROMA_COLLECTION in existing:
        storage.chroma_client.delete_collection(CHROMA_COLLECTION)


def reset_bm25():
    shutil.rmtree(BM25_DIR, ignore_errors=True)


def reset_all(storage):
    """Wipe all three stores together so they can never drift apart."""
    reset_redis(storage)
    reset_chroma(storage)
    reset_bm25()