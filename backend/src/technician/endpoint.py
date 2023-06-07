from fastapi import APIRouter
from fastapi import Query
from typing import Optional, List
import requests
from backend.settings import SERVER_IP, SERVER_PORT, BINANCE_API_URL, BINANCE_API_KEY, BINANCE_API_SECRET_KEY
from backend.config.api_key_handler import get_api_key, get_nlp_api_key
import json

# APIRouter creates path operations for user module
router = APIRouter(
    prefix="/technician",
    tags=["Technician"],
    responses={404: {"description": "Not found"}},
)


@router.get("/status/api/")
def get_api_status(exchange: str = 'binance'):
    print(exchange)
    if BINANCE_API_KEY is None:
        return {'backend_server_status': 'no_api_key'}  # API key is not set
    account_url = f"{BINANCE_API_URL}/api/v3/ping"

    headers = {'X-MBX-APIKEY': BINANCE_API_KEY} # not even needed
    response = requests.get(account_url, headers=headers)
    if response.status_code == 200:  # Check if the request was successful
        # if not response.json():
        #     print(response.json(), BINANCE_API_KEY)
        #     return {'backend_server_status': 'false_api_key'}  # API Key exists but doesnt work
        # else:
        return {'backend_server_status': 'success'}  # Connection to Binance API successful
    else:
        # Request was not successful, return the error message
        return {'backend_server_status': 'api_conn_error'}  # API Key exists but doesnt work
