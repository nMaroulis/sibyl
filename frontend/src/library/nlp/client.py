import requests
import json
from streamlit import cache_resource


@cache_resource(ttl=3600, show_spinner=None)  # cache result for 1 hour2
def fetch_news(website='coindesk', limit=10):
    url = "http://127.0.0.1:8000/reporter/news/articles?website=" + website + "&limit=" + str(limit)
    response = requests.get(url)
    if response.status_code == 200:
        return json.loads(response.json())
    else:
        return None


@cache_resource(ttl=3600, show_spinner=None)  # cache result for 1 hour2
def fetch_news_summary(model='spacy', website='coindesk'):
    url = "http://127.0.0.1:8000/reporter/news/summary?model=" + model + "&website=" + website
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
