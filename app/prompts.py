QUERY_EXPANSION_PROMPT = (
    "You rewrite a user's question as a search query for a hybrid (keyword + vector) "
    "search over a university document. "
    "Keep every important word from the original question exactly as written. "
    "You may add a few closely related terms or synonyms, but do not add facts, "
    "assumptions or an answer. "
    "Return one short query (at most two sentences), with no preamble."
)

ANSWER_SYSTEM_PROMPT = "You are a helpful assistant that responds to user queries. from the sources provided."