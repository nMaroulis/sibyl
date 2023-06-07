from fastapi import APIRouter
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


@router.get("/get_news/{query}")
def get_nlp_api_status(query: str = ''):

    API_TOKEN = get_nlp_api_key()  # nlp_api
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    API_URL = "https://api-inference.huggingface.co/models/deepset/roberta-base-squad2"

    def query(payload):
        data = json.dumps(payload)
        response = requests.request("POST", API_URL, headers=headers, data=data)
        return json.loads(response.content.decode("utf-8"))
    data = query(
        {
            "inputs": {
                "question": "How do you see Bitcoin price tomorrow?",
                "context": "You are a Financial Expert and you have to give your professional .",
            }
        }
    )
    return 0
