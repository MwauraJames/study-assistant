import os
from dotenv import load_dotenv
from langfuse import get_client
from openinference.instrumentation.llama_index import LlamaIndexInstrumentor

load_dotenv()

# Access the specific API key variable
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
LANGFUSE_BASE_URL = os.getenv("LANGFUSE_BASE_URL")


def attach_langfuse_observability():
    langfuse = get_client()
    if not langfuse.auth_check():
        raise RuntimeError("Langfuse auth failed - check keys and LANGFUSE_HOST")
    LlamaIndexInstrumentor().instrument()