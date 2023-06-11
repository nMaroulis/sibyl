import requests


def ask_question(question, context):
    api_key = ""
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }

    data = {
        'prompt': f'Question: {question}\nContext: {context}\nAnswer:',
        'max_tokens': 100,
        'temperature': 0.7,
        'top_p': 1.0,
        'n': 1,
        'stop': None
    }

    response = requests.post(
        'https://api.openai.com/v1/engines/gpt-3.5-turbo/completions',
        headers=headers,
        json=data
    )

    answer = response.json()

    return answer



question = "What is the capital of France?"
context = "France is a country located in Western Europe."

answer = ask_question(question, context)
print("Answer:", answer)
