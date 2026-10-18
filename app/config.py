from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    top_k: int = 50
    merge_ratio: float = 0.5
    chunk_sizes: list[int] = [2048, 512, 128]

    upload_dir: str = "uploads"
    chroma_path: str = "./chroma_db_storage"
    chroma_collection: str = "university_nodes"
    bm25_dir: str = "./bm25_index_storage"
    redis_namespace: str = "university_app_docs"

    temparature: float = 0.2

    rerank_model: str = "rerank-v4.0-pro"
    rerank_top_n: int = 3

    embed_model: str = "BAAI/bge-small-en-v1.5"
    embed_model_cache_dir: str = "./models"