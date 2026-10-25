# app/retrieval/expand.py
from langsmith import traceable
from prompts import QUERY_EXPANSION_PROMPT
from config import Settings

settings = Settings()


@traceable(name="expand_query")
def expand_query(
    model,
    query: str,
    chat_history: list[dict] | None = None,
) -> str:
    """
    Rewrites follow-up questions using recent chat history into a standalone
    search query, then expands it with key terms for Qdrant hybrid search.
    """
    messages = [("system", QUERY_EXPANSION_PROMPT)]

    # Inject recent conversation turns as brief context if available
    if chat_history:
        history_lines = [
            f"{m['role'].upper()}: {m['content']}" for m in chat_history
        ]
        history_block = "\n".join(history_lines)
        user_payload = (
            f"Recent Conversation History:\n{history_block}\n\n"
            f"Latest User Question to rewrite/expand as a standalone search query:\n{query}"
        )
    else:
        user_payload = query

    messages.append(("human", user_payload))

    try:
        response = model.invoke(messages)
        result = (response.content or "").strip()
        return result if result else query
    except Exception as e:
        print(f"[expand_query] fallback to raw query due to error: {e}")
        return query