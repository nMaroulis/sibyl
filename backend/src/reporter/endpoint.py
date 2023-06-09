from fastapi import APIRouter
from reporter.fetch_news import fetch_news
from fastapi import Query
from typing import Optional, List
import requests
from backend.settings import SERVER_IP, SERVER_PORT, BINANCE_API_URL, BINANCE_API_KEY, BINANCE_API_SECRET_KEY
from backend.config.api_key_handler import get_api_key, get_nlp_api_key
import json


# APIRouter creates path operations for user module
router = APIRouter(
    prefix="/reporter",
    tags=["Reporter"],
    responses={404: {"description": "Not found"}},
)


@router.get("/news/{website}")
def get_nlp_api_status(website: str = 'coindesk', limit: int = 10):

    # API_TOKEN = get_nlp_api_key()  # nlp_api
    # API_URL = "https://api-inference.huggingface.co/models/nMaroulis1992/gpt-3.5-turbo"
    # headers = {"Authorization": f"Bearer {API_TOKEN}"}
    # data = {"inputs": "What is 1 plus 1 ?"}
    #
    # response = requests.post(API_URL, headers=headers, json=data)
    # print(response.raise_for_status())
    res = fetch_news(website, limit)

    return res
