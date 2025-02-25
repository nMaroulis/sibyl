from backend.src.reporter.web_crawlers.cointelegraph_crawler import fetch_crypto_articles_from_cointelegraph
from backend.src.reporter.web_crawlers.coindesk_crawler import fetch_coindesk_articles
import time

# Custom cache mechanism
cache = {}

def get_cached_response(key):
    """Retrieve cached response if valid, else return None."""
    if key in cache:
        value, timestamp = cache[key]
        if time.time() - timestamp < 3600:  # 1 hour expiry
            return value
    return None

def set_cached_response(key, value):
    """Store response in cache with timestamp."""
    cache[key] = (value, time.time())


def fetch_news(website: str = 'cointelegraph', limit: int = 10) -> list:

    cache_key = f"news_articles:{website}:{limit}"
    cached = get_cached_response(cache_key)
    if cached:
        return cached

    if website == "cointelegraph":
        articles = fetch_crypto_articles_from_cointelegraph(limit)
    elif website == "coindesk":
        articles = fetch_coindesk_articles(limit)
    else:
        articles = fetch_crypto_articles_from_cointelegraph(limit)

    set_cached_response(cache_key, articles) # update cache

    return articles
