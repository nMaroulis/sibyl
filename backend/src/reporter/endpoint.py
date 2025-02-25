from fastapi import APIRouter, HTTPException
from backend.src.reporter.fetch_news import fetch_news
from backend.src.reporter.text_summarization import get_text_summary
from backend.src.reporter.text_sentiment import get_text_sentiment
from backend.src.llm_hub.llm_client_factory import LLMClientFactory
import json


# APIRouter creates path operations for user module
router = APIRouter(
    prefix="/reporter",
    tags=["Reporter"],
    responses={404: {"description": "Not found"}},
)


@router.get("/news/articles")
def get_latest_articles(website: str = 'cointelegraph', limit: int = 10):

    res = fetch_news(website, limit)
    json_data = json.dumps(res)
    return json_data


@router.get("/news/summary")
def get_news_summary(model: str = 'sumy', website: str = 'cointelegraph'):

    articles = fetch_news(website, 20)
    summary = get_text_summary(model, articles)
    return {'summary': json.dumps(summary)}


@router.get("/news/sentiment")
def get_news_sentiment(model: str = 'vader', website: str = 'cointelegraph'):

    articles = fetch_news(website, 20)
    sentiment = get_text_sentiment(model, articles)
    return {'sentiment_compound': sentiment}


@router.get("/news/chatbot")
def get_news_chatbot_response(llm_api: str, question: str):
    try:
        llm_api = f"{llm_api.lower().replace(" ", "_")}_chatbot"
        chatbot = LLMClientFactory.get_client(llm_api)

        news_summary = get_news_summary()['summary']
        news_sentiment = get_news_sentiment()['sentiment_compound']
        prompt = (f"""You're a crypto expert. Based on the information provided below:"""
                  f"""News Summary: {news_summary} | Sentiment: {news_sentiment} Answer the following question: {question}""")
        res = chatbot.get_response(prompt)
        return {'chat_response': res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))