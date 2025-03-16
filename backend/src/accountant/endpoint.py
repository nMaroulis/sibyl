from fastapi import APIRouter
from fastapi import Query
from typing import Optional, List
import requests
from backend.src.exchange_client.exchange_client_factory import ExchangeClientFactory

# APIRouter creates path operations for user module
router = APIRouter(
    prefix="/accountant",
    tags=["Accountant"],
    responses={404: {"description": "Not found"}},
)


# @router.get("/account/spot/pair/price")
# def get_crypto_pair_price(pair: str = 'BTCUSDT', exchange_client: ExchangeClientFactory = None):# -> float:
#     # API endpoint for ticker price
#     response = BinanceTestnetClient().get_crypto_pair_price(pair)
#     return response


@router.get("/account/spot/balance")
def get_spot_balance(exchange: str, quote_asset_pair: str = None):
    client = ExchangeClientFactory.get_client(exchange)
    response = client.get_spot_balance(quote_asset_pair)
    return response
