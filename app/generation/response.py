# app/generation/response.py
from langsmith import traceable
from prompts import RESPONSE_SYSTEM_PROMPT
from config import Settings

settings = Settings()


@traceable(name="final_response")
def final_response(
    model,
    query: str,
    context: str,
    chat_history: list[dict] | None = None,
) -> str:
    """
    Builds a native multi-turn message list:
      1. System prompt
      2. Past ('human' / 'ai') turns from MongoDB
      3. Current ('human') turn containing the retrieved Source Documents + Question
    """
    messages = [("system", RESPONSE_SYSTEM_PROMPT)]

    # Append prior conversation turns natively so the model tracks dialogue state
    if chat_history:
        for msg in chat_history:
            role = "human" if msg["role"] == "user" else "ai"
            messages.append((role, msg["content"]))

    # Attach the retrieved Qdrant chunks to the current question
    current_turn = (
        f"Source Documents:\n{context}\n\n"
        f"Question: {query}"
    )
    messages.append(("human", current_turn))

    response = model.invoke(messages)
    return response.content