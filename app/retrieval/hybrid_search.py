from langsmith import traceable
from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.llms import MockLLM
from llama_index.core.retrievers import AutoMergingRetriever, QueryFusionRetriever
from llama_index.retrievers.bm25 import BM25Retriever

from ingestion.storage import BM25_DIR

TOP_K = 50          # leaves fetched by EACH of dense and BM25, and kept after fusion
MERGE_RATIO = 0.5   # merge siblings into their parent when MORE than this fraction
                    # of the parent's children were retrieved (see notes below)


def build_hybrid_retriever(storage, embed_model):
    """
    Search leaves first, then merge:
      dense (Chroma) + BM25  ->  RRF fusion (top 50 leaves)
      ->  auto-merge: leaves that share a parent are replaced by that parent,
          every other leaf stays as a leaf.
    """
    docstore = storage.redis()
    vector_store = storage.chroma()

    # BM25 raises an error if top_k is larger than the number of indexed leaves
    # (a short document can have fewer than 50), so cap k at the corpus size.
    k = max(1, min(TOP_K, storage.chroma_collection().count()))

    index = VectorStoreIndex.from_vector_store(vector_store, embed_model=embed_model)
    dense = index.as_retriever(similarity_top_k=k)

    sparse = BM25Retriever.from_persist_dir(BM25_DIR)
    sparse.similarity_top_k = k

    fusion = QueryFusionRetriever(
        [dense, sparse],
        similarity_top_k=k,
        llm=MockLLM(),            # never called: num_queries=1 means no query rewriting
        num_queries=1,
        mode="reciprocal_rerank",  # RRF
        use_async=False,
    )

    storage_context = StorageContext.from_defaults(
        docstore=docstore, vector_store=vector_store
    )
    return AutoMergingRetriever(
        fusion, storage_context, simple_ratio_thresh=MERGE_RATIO, verbose=False
    )


@traceable(run_type="retriever")
def drop_covered_nodes(results, docstore):
    """
    Auto-merging can leave a leaf next to a bigger block that already contains it
    (e.g. a 2048 block built from some 512 siblings, plus a leaf from another 512
    sibling inside it). Drop any node whose ancestor is already in the results.
    """
    ids = {r.node.node_id for r in results}
    kept = []
    for r in results:
        cur, covered = r.node, False
        while cur is not None and cur.parent_node is not None:
            pid = cur.parent_node.node_id
            if pid in ids:
                covered = True
                break
            cur = docstore.get_document(pid, raise_error=False)
        if not covered:
            kept.append(r)
    return kept