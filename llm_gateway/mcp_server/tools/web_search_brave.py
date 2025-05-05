import requests

class WebSearchTool:
    def __init__(self, brave_api_key: str):
        self.api_key = brave_api_key

    def search(self, query: str) -> str:
        url = f"https://api.search.brave.com/res/v1/web/search?q={query}"
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key
        }
        response = requests.get(url, headers=headers)
        data = response.json()
        if "web" in data and "results" in data["web"]:
            return data["web"]["results"][0]["description"]
        return "No relevant search result found."
