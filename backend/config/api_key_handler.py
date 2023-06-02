import json, os

# Function to import API Keys from exchange_api_keys folder
def get_api_key(exchange="binance"):
    file_path = './exchange_api_keys' + exchange + '.json'
    if os.path.exists(file_path): # check filepath
        f = open(file_path, "r")
        api_key = json.load(f)
        f.close()
        return api_key
    else:
        return ImportError
