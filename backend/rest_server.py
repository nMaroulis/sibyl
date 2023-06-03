from fastapi import FastAPI
import uvicorn, requests
from settings import SERVER_IP, SERVER_PORT, BINANCE_API_URL, BINANCE_API_KEY, BINANCE_API_SECRET_KEY
from config.api_key_handler import get_api_key
from typing import List
import hashlib, hmac, json, time

app = FastAPI()


# Route for the root path "/"
@app.get("/")
def read_root():
    return {"Sibyl Server Status": "Running"}


@app.get("/coin/price_history/{symbol}")
def get_price_history(symbol: str, interval: str = '1d', limit: int = 100) -> List[dict]:

    headers = {'X-MBX-APIKEY': BINANCE_API_KEY}
    url = f"{BINANCE_API_URL}/api/v3/klines?symbol={symbol.upper()}USDT&interval={interval}&limit={limit}"
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        try:
            data = response.json()
        except json.JSONDecodeError as error:
            return {"error": "Unable to parse response JSON."}

        price_history = [{"Open Time": entry[0], "Open Price": entry[1]} for entry in data]
        return price_history
    else:
        return {"error": "Failed to fetch price history"}


@app.get("/account/spot/overview")
def get_spot_balance():

    # Binance API endpoint
    account_url = f"{BINANCE_API_URL}/api/v3/account"

    # Request headers and parameters
    headers = {'X-MBX-APIKEY': BINANCE_API_KEY}
    params = {'timestamp': int(time.time() * 1000), }

    # Generate the query string
    query_string = '&'.join([f'{key}={value}' for key, value in params.items()])

    # Create a signature
    signature = hmac.new(BINANCE_API_SECRET_KEY.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()

    # Add the signature to the request parameters
    params['signature'] = signature

    # Send the GET request to Binance API
    response = requests.get(account_url, headers=headers, params=params)
    try:
        data = response.json()
    except json.JSONDecodeError as error:
        return {"error": "Unable to parse response JSON."}

    if response.status_code == 200:  # Check if the request was successful
        spot_balances = {}  # all balance
        locked_earn_balances = {}  # Retrieve the locked Earn balances
        staked_balances = {}  # Retrieve the staked balances

        for asset in data['balances']:
            if float(asset['free']) > 0.0 or float(asset['locked']) > 0.0:
                spot_balances[asset['asset']] = {
                    'free': float(asset['free']),
                    'locked': float(asset['locked'])
                }
                if asset['asset'].startswith('LD'):
                    locked_earn_balances[asset['asset']] = {
                        'free': float(asset['free']),
                        'locked': float(asset['locked'])
                    }
                if asset['asset'].startswith('ST'):
                    staked_balances[asset['asset']] = {
                        'free': float(asset['free']),
                        'locked': float(asset['locked'])
                    }
        # print(json.dumps(spot_balances, indent=4))
        return {'spot_balances': spot_balances,
                'locked_earn_balances': locked_earn_balances,
                'staked_balances': staked_balances,
                }
    else:
        # Request was not successful, return the error message
        return {"error": data['msg']}


# Entry point for running the application
if __name__ == "__main__":

    # Run the application using the Uvicorn server
    uvicorn.run(app, host=SERVER_IP, port=SERVER_PORT)