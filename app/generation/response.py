from langsmith import traceable


system_prompt = "You are a helpful assistant that responds to user queries. from the sources provided." \

@traceable
def final_response(llm,query):
    # Use the LLM to expand the query
    expanded_query = llm(query, system_prompt)
    return expanded_query
