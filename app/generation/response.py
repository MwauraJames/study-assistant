from langsmith import traceable

from prompts import RESPONSE_SYSTEM_PROMPT

from config import Settings

settings = Settings()
system_prompt = RESPONSE_SYSTEM_PROMPT

@traceable
def final_response(model,query):
    messages = [
            ("system", system_prompt),
            ("human", query),
        ]
        
    response = model.invoke(messages)
    result= response.content
        
            
        
    return result