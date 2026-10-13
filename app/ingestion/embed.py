from llama_index.embeddings.fastembed import FastEmbedEmbedding

class Embed:
    def __init__(self):
        pass

    def get_embedding(self):

        embed_model = FastEmbedEmbedding(
            model_name="BAAI/bge-small-en-v1.5",
            cache_dir="./models",  # see the note below
        )

        return embed_model

