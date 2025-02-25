import requests
import json
from streamlit import cache_resource
from frontend.config.config import BACKEND_SERVER_ADDRESS


@cache_resource(ttl=3600, show_spinner=None)  # cache result for 1 hour2
def fetch_news(website: str = 'cointelegraph', limit: int = 10):
    url = f"{BACKEND_SERVER_ADDRESS}/reporter/news/articles?website={website}&limit={limit}"
    response = requests.get(url)
    if response.status_code == 200:
        return json.loads(response.json())
    else:
        return None


@cache_resource(ttl=3600, show_spinner=None)  # cache result for 1 hour
def fetch_news_summary(model: str = 'spacy', website: str = 'cointelegraph'):
    url = f"{BACKEND_SERVER_ADDRESS}/reporter/news/summary?model={model}&website={website}"
    response = requests.get(url)
    if response.status_code == 200:
        try:
            summary = json.loads(response.json()['summary'])
            return summary
        except AttributeError:
            return 'Text Summarization Failed! Check NLP settings'
        except KeyError:
            return 'Text Summarization Failed! Check NLP settings'
        except ValueError:
            return 'Text Summarization Failed! Check NLP settings'
    else:
        return 'Text Summarization Failed! Check NLP settings'


@cache_resource(ttl=3600, show_spinner=None)  # cache result for 1 hour2
def fetch_news_sentiment(model: str= 'vader', website: str = 'cointelegraph'):
    url = f"{BACKEND_SERVER_ADDRESS}/reporter/news/sentiment?model={model}&website={website}"
    response = requests.get(url)
    if response.status_code == 200:
        try:
            sentiment_score = response.json()['sentiment_compound']
            return sentiment_score
        except AttributeError:
            return None
        except KeyError:
            return None
        except ValueError:
            return None
    else:
        return None


def get_chatbot_response(llm_api: str, question: str):

    url = f"{BACKEND_SERVER_ADDRESS}/reporter/news/chatbot?llm_api={llm_api}&question={question}"
    response = requests.get(url)
    if response.status_code == 200:
        try:
            chat_res = response.json()['chat_response']
            return chat_res
        except Exception as e:
            return "LLM Model failed to generate a response."
    else:
        return "LLM Model failed to generate a response."