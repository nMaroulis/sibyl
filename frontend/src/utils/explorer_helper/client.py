import streamlit as st
import requests
import pandas as pd
import datetime
from frontend.config.config import BACKEND_SERVER_ADDRESS


def fetch_blocks(blockchain: str, block_count: int) -> pd.DataFrame | None:
    blockchain_dict = {
        "Bitcoin (BTC)": "bitcoin",
        "Litecoin (LTC)": "litecoin"
    }

    url = f"{BACKEND_SERVER_ADDRESS}/explorer/blockchain/blocks?blockchain={blockchain_dict[blockchain]}&block_count={block_count}"
    response = requests.get(url)

    try:
        if response.json().get("status") == "success":
            blocks = response.json().get("data")
            return pd.DataFrame(blocks)
        else:
            return None
    except Exception as e:
        print(e)
        return None

