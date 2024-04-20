from backend.settings import BINANCE_API_URL, BINANCE_API_KEY, BINANCE_API_SECRET_KEY
import requests
import hmac, hashlib
import time
from datetime import datetime


class Technician:

    def __init__(self):
        pass

    def api_status_check(self):
        return