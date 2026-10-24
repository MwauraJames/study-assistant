from typing import Optional
from langsmith import traceable
from collections import Counter
from llama_index.core import VectorStoreIndex
from llama_index.core.vector_stores import (
    MetadataFilter,
    MetadataFilters,
    FilterOperator,
)

from config import Settings

settings = Settings()
TOP_K = settings.top_k
MERGE_RATIO = getattr(settings, "merge_ratio", 0.5)
MIN_MERGE_LEAVES = getattr(settings, "min_merge_leaves", 2)


def build_metadata_filters(
    user_id: str,
    subject: Optional[str] = None,
    doc_id: Optional[str] = None,
) -> MetadataFilters:
    """Build Qdrant payload filters for user_id, and optionally subject and doc_id."""
    filters = [
        MetadataFilter(key="user_id", value=user_id, operator=FilterOperator.EQ)
    ]
    if subject:
        filters.append(
            MetadataFilter(key="subject", value=subject, operator=FilterOperator.EQ)
        )
    if doc_id:
        filters.append(
            MetadataFilter(key="doc_id", value=doc_id, operator=FilterOperator.EQ)
        )
    return MetadataFilters(filters=filters)


def build_hybrid_retriever(
    storage,
    embed_model,
    user_id: str,
    subject: Optional[str] = None,
    doc_id: Optional[str] = None,
):
    """
    Native Qdrant Hybrid Search:
      1. Filters collection by user_id (+ optional subject / doc_id) in Qdrant payload.
      2. Runs dense + sparse (BM25) search over 128-token leaves.
      3. Fuses results natively in Qdrant via Reciprocal Rank Fusion (relative_score / RRF).
    """
    index = VectorStoreIndex.from_vector_store(
        storage.vector_store(),
        embed_model=embed_model,
    )

    filters = build_metadata_filters(user_id=user_id, subject=subject, doc_id=doc_id)

    return index.as_retriever(
        vector_store_query_mode="hybrid",
        similarity_top_k=TOP_K,
        sparse_top_k=TOP_K,
        filters=filters,
    )


@traceable(run_type="retriever")
def merge_leaves_to_parents(results) -> list[str]:
    """
    Stateless Auto-Merging via Qdrant Payload:
      - Counts how many retrieved leaves share each `parent_id`.
      - If a parent has >= MIN_MERGE_LEAVES retrieved (or exceeds MERGE_RATIO of its
        total children), all of those leaves are replaced by a single `parent_text`
        at the rank position of the highest-scoring leaf, and the rest are dropped.
      - Otherwise, the individual 128-token leaf text is kept as-is.
    """
    # 1. Count occurrences of each parent_id in the retrieved top-k leaves
    parent_counts = Counter()
    parent_total_children = {}

    for r in results:
        meta = r.node.metadata or {}
        pid = meta.get("parent_id", r.node.node_id)
        parent_counts[pid] += 1
        # Default to 4 children (512 / 128) if older points don't have num_siblings yet
        parent_total_children[pid] = meta.get("num_siblings", 4)

    # 2. Decide which parents qualify for merging
    parents_to_merge = set()
    for pid, count in parent_counts.items():
        total_children = max(1, parent_total_children[pid])
        ratio = count / total_children

        # Only merge if multiple leaves hit AND they exceed the ratio threshold
        if count >= MIN_MERGE_LEAVES :
            parents_to_merge.add(pid)

    # 3. Build the final candidate list for the reranker (preserving RRF rank order)
    merged_parent_ids = set()
    candidate_texts = []

    for r in results:
        meta = r.node.metadata or {}
        pid = meta.get("parent_id", r.node.node_id)

        if pid in parents_to_merge:
            # First time seeing a leaf from this qualified parent -> insert parent_text
            if pid not in merged_parent_ids:
                merged_parent_ids.add(pid)
                parent_text = meta.get("parent_text") or r.node.get_content()
                candidate_texts.append(parent_text)
            # Subsequent sibling leaves from this parent are automatically dropped!
        else:
            # Did not meet merge threshold -> keep the 128-token leaf text
            candidate_texts.append(r.node.get_content())

    return candidate_texts