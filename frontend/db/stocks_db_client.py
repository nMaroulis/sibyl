import json

STOCKS_PATH = 'frontend/db/stocks.json'


def get_stocks_list():
    """
    Reads stocks from a JSON file and returns a list of strings in the format "Name [Symbol]".

    Args:

    Returns:
        list: A list of strings formatted as "Name [Symbol]".
    """
    # Read the JSON file
    with open(STOCKS_PATH, "r") as f:
        stock_list = json.load(f)

    # Convert the dictionary to a list of strings
    return [f"{name} [{symbol}]" for symbol, name in stock_list.items()]
