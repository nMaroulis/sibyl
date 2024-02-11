

from config.api_key_handler import get_api_key
from config.api_urls import BINANCE_API, BINANCE_API3, BINANCE_TESTNET_API


# NORMAL BINANCE ACCOUNT
# BINANCE_API_KEY = get_api_key("binance")[0]  # change to binance
# BINANCE_API_SECRET_KEY = get_api_key("binance")[1]
# BINANCE_API_URL = BINANCE_API

SERVER_IP = '127.0.0.1'
SERVER_PORT = 8000

# BINANCE TESTNET
BINANCE_API_KEY = get_api_key("binance_testnet")[0]  # change to binance
BINANCE_API_SECRET_KEY = get_api_key("binance_testnet")[1]
BINANCE_API_URL = BINANCE_TESTNET_API
