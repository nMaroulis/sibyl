from backend.src.exchange_client.exchange_client import ExchangeAPIClient
import requests
import json
from backend.src.analyst.analyst_functions import get_coin_symbol_name_map, update_coin_symbol_name_map
from backend.db.api_keys_db_client import APIEncryptedDatabase
import time
import hmac, hashlib
from datetime import datetime
from binance.client import Client
from binance.exceptions import BinanceAPIException
import logging


class BinanceClient(ExchangeAPIClient):

    def __init__(self):
        super().__init__()
        self.name = 'binance'
        self.api_base_url = 'https://api.binance.com'  # api[1-4]
        api_creds = APIEncryptedDatabase.get_api_key_by_name(self.name)
        if api_creds is None:
            self.client = None
        else:
            self.client = Client(api_creds.api_key, api_creds.secret_key)

    def check_status(self):
        if self.client is None:
            return 'Empty Credentials'
        try:
            self.client.get_account()
            return 'Active'
        except BinanceAPIException:
            return 'Invalid Credentials'

    def get_crypto_pair_price(self, pair: str):
        try:
            price = self.client.get_symbol_ticker(symbol=pair)['price']
            return {"price": price}
        except BinanceAPIException as e:
            return {"error": str(e)}

    def get_spot_balance(self):
        if self.client is None:
            return {"error": "Invalid API credentials"}
        try:
            account_info = self.client.get_account()
            spot_balances = {}
            locked_earn_balances, staked_balances = {}, {}

            for asset in account_info['balances']:
                if float(asset['free']) > 0.0 or float(asset['locked']) > 0.0:
                    pair_price = 1.0
                    if asset['asset'] != 'USDT':
                        fetched_price = self.get_crypto_pair_price(asset['asset'] + 'USDT')
                        if "error" not in fetched_price:
                            pair_price = fetched_price['price']

                    balance_data = {
                        'free': float(asset['free']),
                        'locked': float(asset['locked']),
                        'price': pair_price
                    }

                    spot_balances[asset['asset']] = balance_data
                    if asset['asset'].startswith('LD'):
                        locked_earn_balances[asset['asset']] = balance_data
                    if asset['asset'].startswith('ST'):
                        staked_balances[asset['asset']] = balance_data

            return {
                'spot_balances': spot_balances,
                'locked_earn_balances': locked_earn_balances,
                'staked_balances': staked_balances
            }
        except BinanceAPIException as e:
            return {"error": str(e)}

    def fetch_available_coins(self):
        try:
            exchange_info = self.client.get_exchange_info()
            available_coins = [s['baseAsset'] for s in exchange_info['symbols'] if 'USDT' in s['symbol']]
            return list(set(available_coins))
        except BinanceAPIException as e:
            return {"error": str(e)}

    def fetch_price_history(self, symbol: str = 'BTCUSDT', interval: str = '1d', plot_type: str = 'line', limit: int = 100):
        try:
            klines = self.client.get_klines(symbol=symbol.upper(), interval=interval, limit=limit)

            if plot_type == 'line':
                price_history = [{"Open Time": entry[0], "Open Price": float(entry[1])} for entry in klines]
            else:
                price_history = [{
                    "Open Time": entry[0],
                    "Open Price": float(entry[1]),
                    "Highs": float(entry[2]),
                    "Lows": float(entry[3]),
                    "Closing Price": float(entry[4])
                } for entry in klines]

            return price_history

        except Exception as e:
            print(f"Error fetching price history: {e}")
            return []

    def get_minimum_buy_order(self, symbol: str = "BTCUSDT"):
        try:
            exchange_info = self.client.get_symbol_info(symbol)
            for f in exchange_info['filters']:
                if f['filterType'] == 'NOTIONAL':
                    return {'min_notional': float(f['minNotional'])}
            return {'min_notional': -1}
        except BinanceAPIException as e:
            return {"error": str(e)}

    def post_buy_order(self, trade_from: str, trade_to: str, from_amount: float):
        if self.client is None:
            print("Invalid API credentials")
            return None
        try:
            order = self.client.order_market(symbol=f"{trade_to}{trade_from}", quoteOrderQty=from_amount, side='BUY')
            print(order)
            return order.get('executedQty'), order.get('orderId'), str(datetime.fromtimestamp(order.get('transactTime') // 1000).strftime('%Y-%m-%d %H:%M:%S'))
        except BinanceAPIException as e:
            print("Binance Client :: post_buy_order", str(e))
            return None

    def check_swap_eligibility(self, trade_from: str, trade_to: str, from_amount: float):
        """Checks if a swap is eligible."""
        try:
            response = self.client.convert_request_quote(
                fromAsset=trade_from,
                toAsset=trade_to,
                fromAmount=from_amount,
                walletType='SPOT'
            )
            return response.get("quoteId")
        except BinanceAPIException as e:
            logging.error(f"check_swap_eligibility failed: {e}")
            return None

    def post_swap_order(self, trade_from: str, trade_to: str, from_amount: float):
        """Posts a swap order if eligible."""
        quote_id = self.check_swap_eligibility(trade_from, trade_to, from_amount)
        if not quote_id:
            return None
        try:
            response = self.client.accept_convert_quote(quoteId=quote_id)
            return response.get('orderId'), response.get('toAmount'), datetime.utcnow()
        except BinanceAPIException as e:
            logging.error(f"post_swap_order failed: {e}")
            return None

    def post_sell_order(self, trade_from: str, trade_to: str, quantity: float, sell_order_price: float):
        """Places a limit sell order on Binance."""
        try:
            order = self.client.create_order(
                symbol=f"{trade_from}{trade_to}",
                side=Client.SIDE_SELL,
                type=Client.ORDER_TYPE_LIMIT,
                timeInForce=Client.TIME_IN_FORCE_GTC,
                quantity=quantity,
                price=str(sell_order_price)
            )
            return order.get('orderId')
        except BinanceAPIException as e:
            logging.error(f"post_sell_order failed: {e}")
            return None

    def get_order_status(self, symbol_pair: str, order_id: str):
        """Fetches basic order status."""
        try:
            order = self.client.get_order(symbol=symbol_pair, orderId=order_id)
            return order
        except BinanceAPIException as e:
            logging.error(f"get_order_status failed: {e}")
            return None

    def get_order_status_detailed(self, symbol_pair: str, order_id: str):
        """Fetches detailed order status."""
        try:
            order = self.client.get_order(symbol=symbol_pair, orderId=order_id)
            status_map = {
                'NEW': 'active',
                'PARTIALLY_FILLED': 'partially_completed',
                'FILLED': 'completed',
                'CANCELED': 'cancelled',
                'PENDING_CANCEL': 'cancelled',
                'REJECTED': 'cancelled',
                'EXPIRED': 'cancelled',
            }
            new_status = status_map.get(order.get('status'), 'unknown')
            time_sold = None
            if new_status == 'completed':
                trades = self.client.get_my_trades(symbol=symbol_pair)
                if trades:
                    time_sold = datetime.utcfromtimestamp(trades[-1]['time'] // 1000).strftime('%Y-%m-%d %H:%M:%S')
            return {"status": new_status, "time_sold": time_sold}
        except BinanceAPIException as e:
            logging.error(f"get_order_status_detailed failed: {e}")
            return None

    def test_order(self, symbol: str, side: str, quantity: float, price: float = None,
                           order_type: str = "LIMIT", time_in_force: str = "GTC"):
        """
        Tests if a buy or sell order would work on Binance without executing it.

        :param client: Binance Client object
        :param symbol: Trading pair (e.g., 'BTCUSDT')
        :param side: 'BUY' or 'SELL'
        :param quantity: Order quantity
        :param price: Price for limit orders (optional for market orders)
        :param order_type: Order type ('LIMIT', 'MARKET', etc.)
        :param time_in_force: Time in force for limit orders ('GTC', 'IOC', 'FOK')
        :return: True if the order would be accepted, False otherwise
        """
        try:
            order_params = {
                "symbol": symbol.upper(),
                "side": side.upper(),
                "type": order_type.upper(),
                "quantity": quantity,
            }

            if order_type == "LIMIT":
                if price is None:
                    raise ValueError("Price is required for LIMIT orders")
                order_params["price"] = price
                order_params["timeInForce"] = time_in_force.upper()

            # Test the order
            self.client.create_test_order(**order_params)

            print("Order test successful!")
            return True
        except Exception as e:
            print(f"Order test failed: {e}")
            return False