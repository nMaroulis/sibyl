from fastapi import APIRouter
from fastapi import Query
from typing import Optional, List
import requests
from backend.src.exchange_client.binance_client import BinanceClient
from backend.src.exchange_client.binance_testnet_client import BinanceTestnetClient


# APIRouter creates path operations for user module
router = APIRouter(
    prefix="/accountant",
    tags=["Accountant"],
    responses={404: {"description": "Not found"}},
)


@router.get("/account/spot/pair/price")
def get_crypto_pair_price(pair: str = 'BTCUSDT'):
    # API endpoint for ticker price
    response = BinanceTestnetClient().get_crypto_pair_price(pair)
    return response


@router.get("/account/spot/overview/{exchange_id}")
def get_spot_balance(exchange_id: str = 'binance_testnet'):
    response = BinanceTestnetClient().get_spot_balance()
    return response
