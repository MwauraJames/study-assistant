# retrieval.py
from langsmith import traceable
from llama_index.core import VectorStoreIndex
from llama_index.core.retrievers import QueryFusionRetriever
from llama_index.embeddings.fastembed import FastEmbedEmbedding
from llama_index.retrievers.bm25 import BM25Retriever
from llama_index.core.schema import NodeWithScore
from llama_index.core.llms import MockLLM




TOP_K = 50

def build_hybrid_retriever(storage,embed_model) -> QueryFusionRetriever:
      # see note below
    index = VectorStoreIndex.from_vector_store(storage.chroma(), embed_model=embed_model)

    dense = index.as_retriever(similarity_top_k=TOP_K)
    sparse = BM25Retriever.from_defaults(
        docstore=storage.redis("university_app_leaves"),
        similarity_top_k=TOP_K,
    )

    return QueryFusionRetriever(

        [dense, sparse],
        similarity_top_k=TOP_K,
        llm=MockLLM(),
        num_queries=1,
        mode="reciprocal_rerank",
        use_async=False,
    )

@traceable(run_type="retriever")
def expand_to_parents(results, parent_store):
    seen, expanded = set(), []
    for r in results:                          # results are sorted best-first
        parent = r.node.parent_node
        if parent is None or parent.node_id in seen:
            continue
        seen.add(parent.node_id)
        doc = parent_store.get_document(parent.node_id, raise_error=False)
        if doc is not None:
            expanded.append(NodeWithScore(node=doc, score=r.score))
    return expanded


def fuse_ranked_lists(result_lists, top_k=TOP_K, k=60):
    """RRF across several ranked lists (one per query variant)."""
    scores, nodes = {}, {}
    for results in result_lists:
        for rank, r in enumerate(results):
            nid = r.node.node_id
            nodes[nid] = r.node
            scores[nid] = scores.get(nid, 0.0) + 1.0 / (k + rank + 1)
    ranked = sorted(scores, key=scores.get, reverse=True)[:top_k]
    return [NodeWithScore(node=nodes[n], score=scores[n]) for n in ranked]

@traceable(run_type="retriever")
def hybrid_search(retriever, queries, top_k=TOP_K):
    result_lists = retriever.retrieve(queries)
    return fuse_ranked_lists(result_lists, top_k=top_k)