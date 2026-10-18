from llama_index.embeddings.fastembed import FastEmbedEmbedding


class Embed:
    def get_embedding(self):
        return FastEmbedEmbedding(
            model_name="BAAI/bge-small-en-v1.5",
            cache_dir="./models",
        )