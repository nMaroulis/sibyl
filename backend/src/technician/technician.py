from backend.settings import BINANCE_API_URL, BINANCE_API_KEY, BINANCE_API_SECRET_KEY
import requests
import hmac, hashlib
import time
from datetime import datetime
from backend.src.technician.api_router import APIS
from backend.config.api_key_handler import check_exists
from backend.src.exchange_client.exchange_client_factory import ExchangeClientFactory


class Technician:

    def __init__(self):
        pass

    @staticmethod
    def api_status_check(api_name="all"):
        res = {}
        if api_name == "binance" or api_name == "all" or api_name == "exchanges":
            res['binance'] = ExchangeClientFactory.get_client("binance").check_status()
        if api_name == "binance_testnet" or api_name == "all" or api_name == "exchanges":
            res['binance_testnet'] = ExchangeClientFactory.get_client("binance_testnet").check_status()
        if api_name == "kraken" or api_name == "all" or api_name == "exchanges":
            res['kraken'] = ExchangeClientFactory.get_client("kraken").check_status()
        if api_name == "coinbase" or api_name == "all" or api_name == "exchanges":
            res['coinbase'] = ExchangeClientFactory.get_client("coinbase").check_status()

        if api_name == "openai" or api_name == "all" or api_name == "llms":
            res["openai"] = 'Active' if check_exists("openai") is not None else 'Unavailable'
        if api_name == "gemini" or api_name == "all" or api_name == "llms":
            res["gemini"] = 'Active' if check_exists("gemini") is not None else 'Unavailable'
        if api_name == "hugging_face" or api_name == "all" or api_name == "llms":
            res["hugging_face"] = 'Active' if check_exists("hugging_face") is not None else 'Unavailable'
        if api_name == "coinmarketcap" or api_name == "all" or api_name == "llms":
            res["coinmarketcap"] = 'Active' if check_exists("coinmarketcap") is not None else 'Unavailable'

        # APIS = ['binance', 'binance_testnet', 'kraken', 'coinbase', 'openai', 'gemini', 'hugging_face', 'coinmarketcap']
        return res

