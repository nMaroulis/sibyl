import requests
from bs4 import BeautifulSoup
from typing import List, Tuple

def fetch_crypto_articles_from_cointelegraph(limit: int = 10) -> List[Tuple[str, str, str, str]]:
    """
    Fetches the titles and text of the latest crypto-related articles from CoinTelegraph.

    :param limit: The maximum number of articles to return.
    :return: A list of tuples where each tuple contains the title and text of an article.
    """
    url = "https://cointelegraph.com/tags/markets"

    # Define headers with a user-agent to simulate a regular browser request
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    # Send a GET request to the website with the user-agent header
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Failed to retrieve the webpage. Status code: {response.status_code}")
        return []

    # Parse the page content with BeautifulSoup
    soup = BeautifulSoup(response.content, 'html.parser')

    # Find all article containers
    articles = soup.find_all('span', attrs='post-card-inline__title')

    # List to store article titles and their texts
    articles_list: List[Tuple[str, str, str, str]] = []

    # Iterate over articles up to the limit and extract titles and URLs
    for article in articles[:limit]:
        title_text = article.get_text(strip=True)
        link = article.find_parent('a')  # Find the link to the full article
        subtitle = link.find_next('p', attrs='post-card-inline__text')
        if link and 'href' in link.attrs:
            article_url = "https://cointelegraph.com" + link['href']  # Construct the full URL
            # Fetch the article content from the individual article page
            article_content = fetch_article_text(article_url)
            articles_list.append((title_text, subtitle.get_text(), article_url, article_content))

    return articles_list


def fetch_article_text(url: str) -> str:
    """
    Fetches the article content from a given article URL.

    :param url: The URL of the article.
    :return: The main text content of the article.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"Failed to retrieve the article. Status code: {response.status_code}")
        return "Content not available"

    # Parse the article content with BeautifulSoup
    soup = BeautifulSoup(response.content, 'html.parser')

    # Find the article content
    article_content = soup.find('div', attrs='post__content-wrapper')  # Adjust based on website's structure
    if article_content:
        return article_content.get_text(strip=True)
    else:
        return "Content not available"

