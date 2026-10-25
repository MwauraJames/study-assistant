QUERY_EXPANSION_PROMPT = (
    "You rewrite a user's question as a search query for a hybrid (keyword + vector) "
    "search over a university document. \n"
    "If conversation history is provided, first resolve any pronouns or references "
    "(e.g., 'it', 'that', 'the second method') into explicit nouns based on the history. \n"
    "You may add a few closely related terms or synonyms, but do not add facts, "
    "assumptions or an answer. \n"
    "Return one query, with no preamble."
)

RESPONSE_SYSTEM_PROMPT =(
     "You are a helpful assistant that responds to user queries "
    "from the sources provided. \n"
    "if no source is provided say so and do not answer."
)


