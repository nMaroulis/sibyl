import json
import os


# Function to import API Keys from exchange_api_keys folder
def get_api_key(exchange="binance"):
    file_path = 'backend/config/exchange_api_keys/api_credentials.json'
    # print(file_path)
    if os.path.exists(file_path):  # check filepath
        f = open(file_path, "r")
        api_key = json.load(f)
        f.close()
        try:
            credentials = [api_key[exchange]['api_credentials']['API_Key'], api_key[exchange]['api_credentials']['Secret_Key']]
        except: # if error parsing credentials
            return None
        return credentials
    else: # ImportError
        return None


def get_nlp_api_key(nlp_api="hugging_face"):
    file_path = 'backend/config/exchange_api_keys/api_credentials.json'
    # print(file_path)
    if os.path.exists(file_path):  # check filepath
        f = open(file_path, "r")
        api_key = json.load(f)
        f.close()
        try:
            credentials = api_key[nlp_api]['api_credentials']['Secret_Key']
        except:  # if error parsing credentials
            return None
        return credentials
    else: # ImportError
        return None
