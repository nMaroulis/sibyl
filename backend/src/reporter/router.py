from fastapi import APIRouter, HTTPException, Query
from backend.src.reporter.fetch_news import fetch_news
from backend.src.reporter.text_summarization import get_text_summary
from backend.src.reporter.text_sentiment import get_text_sentiment
import json
from typing import Optional
from grpc import insecure_channel
from backend.config import inference_pb2
from backend.config import inference_pb2_grpc
from dotenv import load_dotenv
import os
from backend.src.reporter.schemas import NewsChatbotResponse


# APIRouter creates path operations for user module
router = APIRouter(
    prefix="/reporter",
    tags=["Reporter"],
    responses={404: {"description": "Not found"}},
)


@router.get("/news/articles")
def get_latest_articles(website: str = Query(default='cointelegraph'), limit: int = Query(default=10)):

    res = fetch_news(website, limit)
    json_data = json.dumps(res)
    return json_data


@router.get("/news/summary")
def get_news_summary(model: str = Query(default='sumy'), website: str = Query(default='cointelegraph')):

    articles = fetch_news(website, 20)
    summary = get_text_summary(model, articles)
    return {'summary': json.dumps(summary)}


@router.get("/news/sentiment")
def get_news_sentiment(model: str = Query(default='vader'), website: str = Query(default='cointelegraph')):

    articles = fetch_news(website, 20)
    sentiment = get_text_sentiment(model, articles)
    return {'sentiment_compound': sentiment}


@router.get("/news/chatbot", response_model=NewsChatbotResponse)
def get_news_chatbot_response(model_source: str = Query(), model_type: str = Query(), question: str = Query(), model_name: Optional[str] = Query(default=None)) -> NewsChatbotResponse:

    try:
        news_summary = get_news_summary()['summary']
        news_sentiment = get_news_sentiment()['sentiment_compound']
        prompt = (f"""You're a crypto expert. Based on the information provided below:"""
                  f"""News Summary: {news_summary} | Sentiment: {news_sentiment} Answer the following question: {question}""")

        load_dotenv('llm_gateway/server_config.env')
        channel = insecure_channel(f"{os.getenv("GRPC_INFERENCE_SERVER_IP")}:{os.getenv("GRPC_INFERENCE_SERVER_PORT")}")
        stub = inference_pb2_grpc.InferenceServiceStub(channel)

        kwargs = {
            "model_source": model_source,
            "model_type": model_type,
            "input_text": prompt
        }
        if model_name:
            kwargs["model_name"] = model_name

        request = inference_pb2.PredictRequest(**kwargs)
        response = stub.Predict(request)

        return {'chat_response': response.output_text}
    except Exception as e:
        print("Reporter :: get_news_chatbot_response", str(e))
        raise HTTPException(status_code=400, detail=str(e))
