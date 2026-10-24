import json
import time
from pathlib import Path
from langsmith import traceable
from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.core.node_parser import HierarchicalNodeParser, get_leaf_nodes

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
                "metadata": n.metadata,
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
def chunk_documents(
    storage,
    embed_model,
    docs,
    user_id: str,
    subject: str,
    doc_id: str,
):
    # 1. Hierarchical split: 512 (parent) -> 128 (leaf) tokens.
    node_parser = HierarchicalNodeParser.from_defaults(chunk_sizes=CHUNK_SIZES)
    all_nodes = node_parser.get_nodes_from_documents(docs)
    leaf_nodes = get_leaf_nodes(all_nodes)

    # 2. Build an in-memory lookup of all nodes so leaves can grab their parent's text.
    node_ById = {n.node_id: n for n in all_nodes}

    for leaf in leaf_nodes:
        parent_id = leaf.parent_node.node_id if leaf.parent_node else leaf.node_id
        
        parent_node = node_ById.get(parent_id, leaf)
        num_siblings = len(parent_node.child_nodes) if parent_node.child_nodes else 1
        
        leaf.metadata.update({
            "user_id": user_id,
            "subject": subject,
            "doc_id": doc_id,
            "parent_id": parent_id,
            "parent_text": parent_node.get_content(),
        })

        # CRITICAL: Exclude payload fields from being concatenated into the
        # 128-token leaf text when computing dense & sparse embeddings!
        excluded_keys = ["parent_text", "parent_id", "user_id", "subject", "doc_id"]
        leaf.excluded_embed_metadata_keys.extend(excluded_keys)
        leaf.excluded_llm_metadata_keys.extend(excluded_keys)

    dump_nodes(all_nodes, leaf_nodes)

    # 3. Index leaves into Qdrant (computes both dense and sparse vectors automatically).
    storage_context = StorageContext.from_defaults(vector_store=storage.vector_store())
    VectorStoreIndex(
        leaf_nodes,
        storage_context=storage_context,
        embed_model=embed_model,
    )

    # 4. Ensure fast keyword indexes exist on user_id, subject, doc_id, and parent_id.
    storage.ensure_payload_indexes()

    '''# 5. Consistency check scoped to this specific doc_id.
    time.sleep(3)
    n_qdrant = storage.count_points(doc_id=doc_id)
    if n_qdrant != len(leaf_nodes):
        raise RuntimeError(
            f"Store mismatch after ingestion for doc_id={doc_id}: "
            f"{len(leaf_nodes)} leaves generated, but {n_qdrant} points in Qdrant."
        ) '''

    return {"nodes": len(all_nodes), "leaves": len(leaf_nodes), "doc_id": doc_id}