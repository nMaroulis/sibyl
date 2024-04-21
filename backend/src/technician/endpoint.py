from fastapi import APIRouter
from fastapi import Query
from typing import Optional, List
import requests
from backend.settings import SERVER_IP, SERVER_PORT, BINANCE_API_URL, BINANCE_API_KEY, BINANCE_API_SECRET_KEY
from backend.config.api_key_handler import get_api_key, get_nlp_api_key
import json
from backend.src.technician.technician import Technician

# APIRouter creates path operations for user module
router = APIRouter(
    prefix="/technician",
    tags=["Technician"],
    responses={404: {"description": "Not found"}},
)

technician_worker = Technician()


@router.get("/status/api/exchange/{exchange_name}")
def get_exchange_api_status(exchange_name: str = 'binance'):
    res = technician_worker.api_status_check(exchange_name)
    return res
    # if BINANCE_API_KEY is None:
    #     return {'backend_server_status': 'no_api_key'}  # API key is not set
    # account_url = f"{BINANCE_API_URL}/api/v3/ping"
    #
    # headers = {'X-MBX-APIKEY': BINANCE_API_KEY}  # not even needed
    # response = requests.get(account_url, headers=headers)
    # if response.status_code == 200:  # Check if the request was successful
    #     # if not response.json():
    #     #     print(response.json(), BINANCE_API_KEY)
    #     #     return {'backend_server_status': 'false_api_key'}  # API Key exists but doesnt work
    #     # else:
    #     return {'backend_server_status': 'success'}  # Connection to Binance API successful
    # else:
    #     # Request was not successful, return the error message
    #     return {'backend_server_status': 'api_conn_error'}  # API Key exists but doesnt work


@router.get("/status/api/{api_name}")
def get_api_status(api_name: str = 'binance'):
    try:
        res = technician_worker.api_status_check(api_name)
    except Exception as e:
        print(f"TECHNICIAN :: status/api/all :: {e}")
        res = {}
    return res
