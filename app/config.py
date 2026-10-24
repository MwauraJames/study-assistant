from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    top_k: int = 50
    merge_ratio: float = 0.5       # Merge when > 50% of a parent's leaves are retrieved
    min_merge_leaves: int = 3
    chunk_sizes: list[int] = [512, 128]

    chunked_dir: str = "chunked_content"
    parsed_dir: str = "parsed_content"
    upload_dir: str = "uploads"

    # Qdrant Configuration (defaults to local Docker/server instance; can also use path="./qdrant_storage")
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: Optional[str] = None
    qdrant_collection: str = "university_nodes"
    sparse_model: str = "Qdrant/bm25"

    temparature: float = 0.2

    rerank_model: str = "rerank-v4.0-pro"
    rerank_top_n: int = 4

    embed_model: str = "BAAI/bge-large-en-v1.5"
    embed_model_cache_dir: str = "./models"

settings = Settings()