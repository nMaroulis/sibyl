from fastapi import APIRouter
from fastapi import Query
from typing import Any, Dict
import requests
from backend.src.exchange_client.exchange_client_factory import ExchangeClientFactory

# APIRouter creates path operations for user module
router = APIRouter(
    prefix="/accountant",
    tags=["Accountant"],
    responses={404: {"description": "Not found"}},
)


@router.get("/account/spot/balance")
def get_spot_balance(exchange: str, quote_asset_pair: str = None) -> Dict[str, Any]:
    client = ExchangeClientFactory.get_client(exchange)
    response = client.get_spot_balance(quote_asset_pair)
    return response


@router.get("/account/information")
def get_spot_balance(exchange: str) -> Dict[str, Any]:
    client = ExchangeClientFactory.get_client(exchange)
    response = client.get_account_information()
    return response
