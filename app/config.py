from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    top_k: int = 10
    merge_ratio: float = 1.0
    chunk_sizes: list[int] = [512, 128]

    chunked_dir : str = "chunked_content"
    parsed_dir : str = "parsed_content"
    upload_dir: str = "uploads"
    chroma_path: str = "./chroma_db_storage"
    chroma_collection: str = "university_nodes"
    bm25_dir: str = "./bm25_index_storage"
    redis_namespace: str = "university_app_docs"

    temparature: float = 0.2

    rerank_model: str = "rerank-v4.0-pro"
    rerank_top_n: int = 2

    embed_model: str = "BAAI/bge-large-en-v1.5"
    embed_model_cache_dir: str = "./models"

settings=Settings()