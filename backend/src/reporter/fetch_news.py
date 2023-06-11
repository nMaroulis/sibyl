import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import json


def fetch_coindesk_articles(website='coindesk', limit=10):
    articles = []
    page = ''
    page_num = 1
    while len(articles) < limit:
        url = 'https://www.coindesk.com/tag/bitcoin/' + page
        req = requests.get(url)
        bs = BeautifulSoup(req.text, 'html.parser')
        for article in bs.find_all('div', {'class': 'articleTextSection'}):
            try:
                if article.find("a", {'class': 'category'}).text == 'Markets':
                    # print(article.find("a", {'class': 'card-title'}).text)
                    # print(article.find("a", {'class': 'card-title'})['href'])
                    if len(articles) < limit:
                        articles.append([article.find("a", {'class': 'card-title'}).text, article.find("a", {'class': 'card-title'})['href']])
            except AttributeError:
                pass
            except KeyError:
                pass
        page_num += 1; page = str(page_num)
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


def fetch_news(website='coindesk', limit=10):

    articles = fetch_coindesk_articles()
    response_articles = []
    if len(articles) > 0:
        for article in articles:
            article_title = article[0]
            article_link = article[1]
            article_subtitle, article_body = fetch_coindesk_article_body(article_link)
            # print(article_subtitle)
            response_articles.append([article_title, article_subtitle, article_link, article_body])

    # json_data = json.dumps(response_articles)
    return response_articles # json_data
