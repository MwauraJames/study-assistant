
from langsmith import traceable


system_prompt = "You are a helpful assistant that expands user queries " \
"to be more detailed and specific for a next step of Hybrid Search from a vector database." \
"Do not add any additional information or context, only expand the query to be more specific and detailed." \
"Return only the expanded query, no preamble"

@traceable
def expand_query(llm,query):
    # Use the LLM to expand the query
    expanded_query = llm(query, system_prompt)
    return expanded_query
