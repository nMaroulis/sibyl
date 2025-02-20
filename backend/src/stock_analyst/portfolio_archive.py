import requests


def fetch_senate_trades():
    url = "https://senate-stock-watcher-data.s3-us-west-2.amazonaws.com/aggregate/all_transactions.json"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    return []
