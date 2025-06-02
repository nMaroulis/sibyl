import requests
from frontend.config.config import BACKEND_SERVER_ADDRESS
from streamlit import warning, sidebar
from typing import Optional


def fetch_wiki_rag_response(model_source: str, model_type: str, model_name: Optional[str], query: str, agent_type: bool) -> str:

    agent_type = "wiki_agent" if agent_type else "wiki_rag"

    url = f"{BACKEND_SERVER_ADDRESS}/wiki/chatbot/query?model_source={model_source}&model_type={model_type}&query={query}&agent_type={agent_type}"
    if model_name:
        url += f"&model_name={model_name}"

    response = requests.get(url)
    if response.status_code == 200:
        res = response.json()
        return res['data']
    else:
        return "Something went wrong, please rephrase and ask again..."


def fetch_vectorstore_status() -> (bool, bool):
    url = f"{BACKEND_SERVER_ADDRESS}/wiki/rag/vectorstore/status"
    response = requests.get(url)
    if response.status_code == 200:
        res = response.json()
        return True if res['embeddings_db'] == "yes" else False
    else:
        return None
