import os
from pyexpat.errors import messages
from dotenv import load_dotenv
from langsmith import traceable
from llama_index.llms.groq import Groq
from llama_index.core.llms import ChatMessage
from typer import prompt

load_dotenv()

# Access the specific API key variable
api_key = os.getenv("GROQ_API_KEY")

llm = Groq(model="openai/gpt-oss-120b",
           temperature=0.2,
            api_key=api_key)

@traceable(run_type="llm")
def generate_response(prompt,system_prompt):
    
    messages = [
        ChatMessage(
            role="system", content=system_prompt
        ),
        ChatMessage(role="user", content=prompt),
    ]

    result= llm.chat(messages)

    

    return result.message.content
