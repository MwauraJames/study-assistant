from langsmith import traceable

system_prompt = (
    "You rewrite a user's question as a search query for a hybrid (keyword + vector) "
    "search over a university document. "
    "Keep every important word from the original question exactly as written. "
    "You may add a few closely related terms or synonyms, but do not add facts, "
    "assumptions or an answer. "
    "Return one short query (at most two sentences), with no preamble."
)


@traceable
def expand_query(llm, query):
    try:
        expanded = (llm(query, system_prompt) or "").strip()
    except Exception:
        expanded = ""
    # If the LLM fails or returns nothing, search with the original question
    # instead of crashing or searching on an empty string.
    return expanded or query