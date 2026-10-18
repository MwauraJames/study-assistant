from models import model

messages = [
    ("system", "You are a concise study assistant."),
    ("human", "hello"),
]
response = model.invoke(messages, temperature=0.2, max_tokens=500)
print(response.content)