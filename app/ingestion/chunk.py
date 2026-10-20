from langsmith import traceable
from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.node_parser import HierarchicalNodeParser, get_leaf_nodes
from llama_index.retrievers.bm25 import BM25Retriever
import json 
from pathlib import Path

from ingestion.storage import BM25_DIR
from config import Settings
settings = Settings()

CHUNK_SIZES = settings.chunk_sizes
CHUNKED_DIR = Path(settings.chunked_dir)
CHUNKED_DIR.mkdir(exist_ok=True)

def dump_nodes(all_nodes, leaf_nodes):
    """Write the chunks to disk so you can inspect them. Never fails an ingestion."""
    try:
        out_dir = Path(settings.chunked_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        leaf_ids = {n.node_id for n in leaf_nodes}

        records = []
        for n in all_nodes:
            if n.node_id in leaf_ids:
                level = "leaf"
            elif n.parent_node is None:
                level = "root"
            else:
                level = "mid"
            text = n.get_content()
            records.append({
                "id": n.node_id,
                "level": level,
                "parent_id": n.parent_node.node_id if n.parent_node else None,
                "num_children": len(n.child_nodes or []),
                "words": len(text.split()),
                "text": text,
            })

        (out_dir / "all_nodes.json").write_text(
            json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        blocks = [
            f"=== {r['level']} | id {r['id'][:8]} | parent {str(r['parent_id'])[:8]} | {r['words']} words ===\n{r['text']}"
            for r in records if r["level"] == "leaf"
        ]
        (out_dir / "leaves.md").write_text("\n\n".join(blocks), encoding="utf-8")
    except Exception as e:
        print(f"[dump_nodes] skipped: {e}")

@traceable
def chunk_documents(storage, embed_model, docs):
    # 1. Hierarchical split: 2048 -> 512 -> 128 tokens.
    #    get_nodes_from_documents returns ALL levels; leaves are the 128-token ones.
    node_parser = HierarchicalNodeParser.from_defaults(chunk_sizes=CHUNK_SIZES)
    all_nodes = node_parser.get_nodes_from_documents(docs)
    leaf_nodes = get_leaf_nodes(all_nodes)
    dump_nodes(all_nodes, leaf_nodes) 

    # 2. Redis docstore: EVERY node (all levels). The auto-merging step looks up
    #    parents by id here. (The separate "leaves" namespace is gone: BM25 is built
    #    straight from leaf_nodes in memory, so it can't drift from the other stores.)
    docstore = storage.redis()
    docstore.add_documents(all_nodes)

    # 3. Chroma: leaves only, embedded.
    storage_context = StorageContext.from_defaults(
        docstore=docstore, vector_store=storage.chroma()
    )
    VectorStoreIndex(leaf_nodes, storage_context=storage_context, embed_model=embed_model)

    # 4. BM25 over the same leaves, persisted to disk.
    bm25 = BM25Retriever.from_defaults(nodes=leaf_nodes)
    bm25.persist(BM25_DIR)

    # 5. Consistency check: fail loudly now instead of returning odd results later.
    n_chroma = storage.chroma_collection().count()
    if n_chroma != len(leaf_nodes):
        raise RuntimeError(
            f"Store mismatch after ingestion: {len(leaf_nodes)} leaves but "
            f"{n_chroma} vectors in Chroma."
        )

    return {"nodes": len(all_nodes), "leaves": len(leaf_nodes)}