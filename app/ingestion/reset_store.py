from qdrant_client.http import models as rest


def delete_by_doc_id(storage, doc_id: str):
    """Delete all points belonging to a single document without affecting other users/docs."""
    if not storage.client.collection_exists(storage.collection_name):
        return

    storage.client.delete(
        collection_name=storage.collection_name,
        points_selector=rest.FilterSelector(
            filter=rest.Filter(
                must=[
                    rest.FieldCondition(
                        key="doc_id",
                        match=rest.MatchValue(value=doc_id),
                    )
                ]
            )
        ),
    )


def reset_all(storage):
    """Wipe the entire Qdrant collection (use only for dev resets, not per-upload)."""
    if storage.client.collection_exists(storage.collection_name):
        storage.client.delete_collection(storage.collection_name)
    storage._vector_store = None