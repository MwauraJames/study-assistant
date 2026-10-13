import os
from dotenv import load_dotenv
import cohere
from langsmith import traceable

load_dotenv()

COHERE_API_KEY = os.getenv("COHERE_API_KEY")

co = cohere.ClientV2(COHERE_API_KEY)

@traceable
def rerank_documents(query, documents,model, top_n=3):
    response = co.rerank(
        model=model,
        query=query,
        documents=documents,
        top_n=top_n,
    )


    return response


