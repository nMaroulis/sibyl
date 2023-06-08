import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json


def fetch_coindesk_articles():
    url = 'https://www.coindesk.com/tag/bitcoin/'
    req = requests.get(url)
    bs = BeautifulSoup(req.text, 'html.parser')
    articles = []
    for article in bs.find_all("a", {'class': 'card-title'}):
        try:
            title = article.text  # Get Header
            href = article["href"]  # Get Article Link
            body = None
            # body = bs.find("p", {'class': 'desc'}).text
            articles.append([title, href])
        except AttributeError:
            pass
    return articles


def fetch_coindesk_article_body(article_url):
    url = 'https://www.coindesk.com' + article_url
    req = requests.get(url)
    if req.status_code == 200:
        bs = BeautifulSoup(req.text, 'html.parser')
        subtitle = None
        article_body = []
        # Get Article subtitle
        try:
            # title = bs.find('h1').text  # Get Header
            subtitle = bs.find('h2').text
        except AttributeError:
            pass
        # Get article body elements
        for article in bs.select("p:not([class])"):  # The paragraph elements with no class contain the body of the article
            try:
                article_body.append(article.text)
            except KeyError:
                pass
            except AttributeError:
                pass
        return subtitle, article_body
    else:
        return []


def fetch_news(website='coindesk'): # https://decrypt.co/news

    articles = fetch_coindesk_articles()
    response_articles = []
    if len(articles) > 0:
        for article in articles:
            article_title = article[0]
            article_link = article[1]
            article_subtitle, article_body = fetch_coindesk_article_body(article_link)
            print(article_subtitle)
            response_articles.append([article_title, article_subtitle, article_link, article_body])

    json_data = json.dumps(response_articles)
    return json_data
