import json
import os

CREDENTIALS_FILE_PATH = 'backend/config/api_keys/api_credentials.json'


def init_json(exchange="binance"):
    if os.path.exists(CREDENTIALS_FILE_PATH):  # check filepath
        f = open(CREDENTIALS_FILE_PATH, "r")
        api_key = json.load(f)
        f.close()
        try:
            credentials = [api_key[exchange]['api_credentials']['API_Key'], api_key[exchange]['api_credentials']['Secret_Key']]
        except Exception as e:  # if error parsing credentials
            return None
        return credentials
    else: # ImportError
        return None


# Function to import API Keys from api_keys folder
def get_api_key(exchange: str) -> list[str | None]:
    if os.path.exists(CREDENTIALS_FILE_PATH):  # check filepath
        f = open(CREDENTIALS_FILE_PATH, "r")
        api_key = json.load(f)
        f.close()
        try:
            credentials = [api_key[exchange]['api_credentials']['API_Key'], api_key[exchange]['api_credentials']['Secret_Key']]
        except Exception as e:  # if error parsing credentials
            return [None, None]
        return credentials
    else: # ImportError
        return [None, None]


def get_nlp_api_key(nlp_api: str = "hugging_face") -> str | None:
    if os.path.exists(CREDENTIALS_FILE_PATH):  # check filepath
        f = open(CREDENTIALS_FILE_PATH, "r")
        api_key = json.load(f)
        f.close()
        try:
            credentials = api_key[nlp_api]['api_credentials']['Secret_Key']
        except:  # if error parsing credentials
            return None
        return credentials
    else: # ImportError
        return None


def get_binance_testnet_api_keys():
    if os.path.exists(CREDENTIALS_FILE_PATH):  # check filepath
        f = open(CREDENTIALS_FILE_PATH, "r")
        api_key = json.load(f)
        f.close()
        try:
            credentials = api_key['binance_testnet']['api_credentials']['Secret_Key']
        except:  # if error parsing credentials
            return None
        return credentials
    else:  # ImportError
        return None


def get_coinmarketcap_api_key():
    if os.path.exists(CREDENTIALS_FILE_PATH):  # check filepath
        f = open(CREDENTIALS_FILE_PATH, "r")
        api_key = json.load(f)
        f.close()
        try:
            credentials = api_key['coinmarketcap']['api_credentials']['API_Key']
        except:  # if error parsing credentials
            return None
        return credentials
    else:  # ImportError
        return None


def check_exists(api_name):
    if os.path.exists(CREDENTIALS_FILE_PATH):
        f = open(CREDENTIALS_FILE_PATH, "r")
        api_key = json.load(f)
        f.close()
        try:
            credentials = api_key[api_name]['api_credentials']['API_Key']
        except Exception as e:  # if error parsing credentials
            return None
        return credentials
    else: # ImportError
        return None
