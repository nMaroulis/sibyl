import requests
from streamlit import cache_data
from frontend.config.config import BACKEND_SERVER_ADDRESS
import re


def extract_coin_symbol(text):
    match = re.search(r'\[([^\]]+)\]$', text)
    return match.group(1) if match else text
