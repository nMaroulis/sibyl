from fastapi import FastAPI
import uvicorn, requests
from settings import SERVER_IP, SERVER_PORT

app = FastAPI()


class Item: # Data model for an item
    def __init__(self, name: str, price: float):
        self.name = name
        self.price = price


# Route for the root path "/"
@app.get("/")
def read_root():
    return {"Sibyl Server Status": "Running"}


@app.get("/coin/price_history/{symbol}")
def get_price_history(symbol: str, interval: str = '1d', limit: int = 100) -> list[dict]:
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol.upper()}USDT&interval={interval}&limit={limit}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        price_history = [{"Open Time": entry[0], "Open Price": entry[1]} for entry in data]
        return price_history
    else:
        return {"error": "Failed to fetch price history"}


# Entry point for running the application
if __name__ == "__main__":

    # Run the application using the Uvicorn server
    uvicorn.run(app, host=SERVER_IP, port=SERVER_PORT)
