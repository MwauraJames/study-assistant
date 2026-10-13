
def reset_redis(storage):
    for ns in ("university_app_docs", "university_app_leaves"):
        store = storage.redis(ns)
        for doc_id in list(store.docs):          # list() so we don't mutate while iterating
            store.delete_document(doc_id, raise_error=False)
def reset_chroma(storage):
    client = storage.chroma()
    try:
        client.delete_collection("university_nodes")
    except Exception:       # collection didn't exist yet
        pass