import os
from dotenv import load_dotenv
from pathlib import Path

from llama_cloud import LlamaCloud

load_dotenv()

# Access the specific API key variable
api_key = os.getenv("LLAMA_CLOUD_API_KEY")


client = LlamaCloud()  # Uses LLAMA_CLOUD_API_KEY env var

# Upload and parse a document
file = client.files.create(file="test.txt", purpose="parse")
result = client.parsing.parse(
    file_id=file.id,
    tier="agentic",
    version="latest",
    processing_options={ 
        "cost_optimizer" : {
                    "enable": True
                    }
        },
    expand=["markdown"],
)

print(result.markdown.pages[0].markdown)
