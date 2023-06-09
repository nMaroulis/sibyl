import requests
import json
from streamlit import cache_resource


@cache_resource(ttl=3600, show_spinner=None)  # cache result for 1 hour2
def fetch_news(website='coindesk', limit=10):
    url = "http://127.0.0.1:8000/reporter/news/" + website
    response = requests.get(url)
    if response.status_code == 200:
        return json.loads(response.json())
    else:
        return None
