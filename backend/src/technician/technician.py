
from database.api_keys_db_client import APIEncryptedDatabase
from backend.src.exchange_client.exchange_client_factory import ExchangeClientFactory

class Technician:

    def __init__(self):
        pass

    @staticmethod
    def api_status_check(api_name: str ="all") -> dict:  # TODO reexamine this func
        res = {}
        if api_name == "binance" or api_name == "all" or api_name == "exchanges":
            res['binance'] = ExchangeClientFactory.get_client("binance").check_status()
            print(res['binance'])
        if api_name == "binance_testnet" or api_name == "all" or api_name == "exchanges":
            res['binance_testnet'] = ExchangeClientFactory.get_client("binance_testnet").check_status()
            print(res['binance_testnet'])
        if api_name == "kraken" or api_name == "all" or api_name == "exchanges":
            res['kraken'] = ExchangeClientFactory.get_client("kraken").check_status()
            print(res['kraken'])
        if api_name == "coinbase" or api_name == "all" or api_name == "exchanges":
            res['coinbase'] = ExchangeClientFactory.get_client("coinbase").check_status()
            print(res['coinbase'])
        # if api_name == "coinbase_sandbox" or api_name == "all" or api_name == "exchanges":
        #     res['coinbase_sandbox'] = ExchangeClientFactory.get_client("coinbase_sandbox").check_status()
        #     print(res['coinbase_sandbox'])

        if api_name == "openai" or api_name == "all" or api_name == "llms":
            res["openai"] = 'Active' if APIEncryptedDatabase.get_api_key_by_name("openai") is not None else 'Unavailable'
        if api_name == "gemini" or api_name == "all" or api_name == "llms":
            res["gemini"] = 'Active' if APIEncryptedDatabase.get_api_key_by_name("gemini") is not None else 'Unavailable'
        if api_name == "hugging_face" or api_name == "all" or api_name == "llms":
            res["hugging_face"] = 'Active' if APIEncryptedDatabase.get_api_key_by_name("hugging_face") is not None else 'Unavailable'
        if api_name == "coinmarketcap" or api_name == "all":
            res["coinmarketcap"] = 'Active' if APIEncryptedDatabase.get_api_key_by_name("coinmarketcap") is not None else 'Unavailable'
        return res


    @staticmethod
    def insert_api_key_to_db(api_name: str, api_key: str, secret_key: str, api_metadata: str) -> bool:
        try:
            if APIEncryptedDatabase.get_api_key_by_name(api_name):
                APIEncryptedDatabase.update_api_key(api_name, api_key, secret_key, api_metadata)
            else:
                APIEncryptedDatabase.insert_api_key(api_name, api_key, secret_key, api_metadata)
            return True
        except Exception as e:
            print(e)
            return False
