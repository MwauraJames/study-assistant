import os
from dotenv import load_dotenv
import cohere
from langsmith import traceable
from config import Settings

settings = Settings()

load_dotenv()

COHERE_API_KEY = os.getenv("COHERE_API_KEY")

co = cohere.ClientV2(COHERE_API_KEY)
model = settings.rerank_model
top_n=settings.rerank_top_n

@traceable
def rerank_documents(query, documents):
    response = co.rerank(
        model=model,
        query=query,
        documents=documents,
        top_n=top_n,
    )


    return response


