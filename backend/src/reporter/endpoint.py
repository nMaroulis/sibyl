from fastapi import APIRouter
from backend.src.reporter.fetch_news import fetch_news
from backend.src.reporter.text_summarization import get_text_summary
from backend.src.reporter.text_sentiment import get_text_sentiment
from fastapi import Query
from typing import Optional, List
from backend.config.api_key_handler import get_nlp_api_key
import json


# APIRouter creates path operations for user module
router = APIRouter(
    prefix="/reporter",
    tags=["Reporter"],
    responses={404: {"description": "Not found"}},
)


@router.get("/news/articles")
def get_nlp_api_status(website: str = 'cointelegraph', limit: int = 10):

    # API_TOKEN = get_nlp_api_key()  # nlp_api
    # API_URL = "https://api-inference.huggingface.co/models/nMaroulis1992/gpt-3.5-turbo"
    # headers = {"Authorization": f"Bearer {API_TOKEN}"}
    # data = {"inputs": "What is 1 plus 1 ?"}
    #
    # response = requests.post(API_URL, headers=headers, json=data)
    # print(response.raise_for_status())
    res = fetch_news(website, limit)
    json_data = json.dumps(res)
    return json_data


@router.get("/news/summary")
def get_news_summary(model: str = 'sumy', website: str = 'cointelegraph'):

    print(model, website)
    articles = fetch_news(website, 20)
    summary = get_text_summary(model, articles)
    return {'summary': json.dumps(summary)}


@router.get("/news/sentiment")
def get_news_sentiment(model: str = 'vader', website: str = 'cointelegraph'):

    articles = fetch_news(website, 20)

    print(len(articles))
    sentiment = get_text_sentiment(model, articles)
    print(sentiment)
    return {'sentiment_compound': sentiment}
