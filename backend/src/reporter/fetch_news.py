from backend.src.reporter.web_crawlers.cointelegraph_crawler import fetch_crypto_articles_from_cointelegraph
from backend.src.reporter.web_crawlers.coindesk_crawler import fetch_coindesk_articles


def fetch_news(website: str = 'cointelegraph', limit: int = 10) -> list:

    if website == "cointelegraph":
        articles = fetch_crypto_articles_from_cointelegraph(limit)
    elif website == "coindesk":
        articles = fetch_coindesk_articles(limit)
    else:
        articles = fetch_crypto_articles_from_cointelegraph(limit)

    return articles
