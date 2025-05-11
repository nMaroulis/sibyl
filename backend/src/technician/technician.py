from database.api_keys_db_client import APIEncryptedDatabase
from backend.src.exchange_client.exchange_client_factory import ExchangeClientFactory
from llm_gateway.llm_models.llm_client_factory import LLMClientFactory
from typing import Dict, List


class Technician:

    def __init__(self):
        pass

    @staticmethod
    def api_status_check(api_name: str ="all") -> Dict[str, str]:
        res = {}
        if api_name in ["all", "exchanges", "binance"]:
            res['binance'] = ExchangeClientFactory.get_client("binance").check_status()
        if api_name in ["all", "exchanges", "binance_testnet"]:
            res['binance_testnet'] = ExchangeClientFactory.get_client("binance_testnet").check_status()
        if api_name in ["all", "exchanges", "kraken"]:
            res['kraken'] = ExchangeClientFactory.get_client("kraken").check_status()
        if api_name in ["all", "exchanges", "coinbase"]:
            res['coinbase'] = ExchangeClientFactory.get_client("coinbase").check_status()
        if api_name in ["all", "exchanges", "coinbase_sandbox"]:
            res['coinbase_sandbox'] = ExchangeClientFactory.get_client("coinbase_sandbox").check_status()
        if api_name in ["all", "exchanges", "mock_exchange"]:
            res['mock_exchange'] = ExchangeClientFactory.get_client("mock_exchange").check_status()

        if api_name in ["all", "llms", "openai"]:
            res["openai"] = 'Active' if APIEncryptedDatabase.get_api_key_by_name("openai") is not None else 'Unavailable'
        if api_name in ["all", "llms", "gemini"]:
            res["gemini"] = 'Active' if APIEncryptedDatabase.get_api_key_by_name("gemini") is not None else 'Unavailable'
        if api_name in ["all", "llms", "hugging_face"]:
            res["hugging_face"] = 'Active' if APIEncryptedDatabase.get_api_key_by_name("hugging_face") is not None else 'Unavailable'

        if api_name in ["all", "llms", "llama_cpp"]:
            res["llama_cpp"] = 'Active' if APIEncryptedDatabase.get_api_key_by_name("llama_cpp") is not None else 'Unavailable'
        if api_name in ["all", "llms", "tgi"]:
            res["tgi"] = 'Active' if APIEncryptedDatabase.get_api_key_by_name("tgi") is not None else 'Unavailable'

        if api_name in ["all", "coinmarketcap"]:
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


    def get_local_models(self, library: str) -> List[str]:
        llm = LLMClientFactory.get_client(model_type=library)
        models = llm.get_available_models()
        return models