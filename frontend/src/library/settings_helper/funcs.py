from frontend.src.library.settings_helper.client import post_exchange_api_keys

def insert_update_exchange_api_keys(exchange: str, api_key: str, secret_key: str) -> bool:
    exchange = exchange.lower().replace(' ', '_')
    res = post_exchange_api_keys(exchange, api_key, secret_key)
    return res