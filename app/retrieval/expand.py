from langsmith import traceable
from prompts import QUERY_EXPANSION_PROMPT

from config import Settings

settings = Settings()

system_prompt = QUERY_EXPANSION_PROMPT


@traceable
def expand_query(model,query):
    messages = [
            ("system", system_prompt),
            ("human", query),
        ]
    
    response = model.invoke(messages)
    result= response.content
    
        
    
    return result
    