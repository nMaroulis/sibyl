import requests
from frontend.config.config import BACKEND_SERVER_ADDRESS



def fetch_wiki_rag_response(user_query: str):
    url = f"{BACKEND_SERVER_ADDRESS}/wiki/chatbot/query?query={user_query}"
    response = requests.get(url)
    if response.status_code == 200:
        res = response.json()
        return res['data']
    else:
        return "Something went wrong, please rephrase and ask again..."
