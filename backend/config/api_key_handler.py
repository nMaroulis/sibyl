import json
import os


# Function to import API Keys from exchange_api_keys folder
def get_api_key(exchange="binance"):
    file_path = 'backend/config/exchange_api_keys/api_credentials.json'
    print(file_path)
    if os.path.exists(file_path):  # check filepath
        f = open(file_path, "r")
        api_key = json.load(f)
        f.close()
        return api_key[exchange]['api_credentials']['API_Key']
    else:
        return ImportError
