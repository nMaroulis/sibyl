from frontend.src.library.settings_helper.client import post_new_api_keys

def insert_update_api_keys(exchange: str, api_key: str, secret_key: str = None, api_metadata: str = None) -> bool:
    exchange = exchange.lower().replace(' ', '_')
    res = post_new_api_keys(exchange, api_key, secret_key, api_metadata)
    return res