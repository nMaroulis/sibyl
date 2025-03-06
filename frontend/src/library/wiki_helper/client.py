import requests
from frontend.config.config import BACKEND_SERVER_ADDRESS
from streamlit import success, warning


def fetch_wiki_rag_response(user_query: str):
    url = f"{BACKEND_SERVER_ADDRESS}/wiki/chatbot/query?query={user_query}"
    response = requests.get(url)
    if response.status_code == 200:
        res = response.json()
        return res['data']
    else:
        return "Something went wrong, please rephrase and ask again..."


def fetch_wiki_status() -> (bool, bool):
    url = f"{BACKEND_SERVER_ADDRESS}/wiki/rag/status"
    response = requests.get(url)
    if response.status_code == 200:
        res = response.json()

        valid_db = False
        llm_api = False
        if res['embeddings_db'] == "yes":
            success("**Embeddings Database** is successfully retrieved.", icon=":material/task_alt:")
            valid_db = True
        else:
            warning("**Embeddings Database** was not found on your filesystem.", icon=":material/warning_alt:")


        if res['llm_api'] == "yes":
            success("A **valid LLM API key** is successfully found.", icon=":material/task_alt:")
            llm_api = True
        else:
            warning("A **valid LLM API key** was not found in the Encrypted DB.", icon=":material/warning_alt:")

        return valid_db, llm_api
    else:
        return None
