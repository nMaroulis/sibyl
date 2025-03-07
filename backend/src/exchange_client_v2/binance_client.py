from backend.src.exchange_client_v2.exchange_client import ExchangeAPIClient
from database.api_keys_db_client import APIEncryptedDatabase
from binance.client import Client
from binance.exceptions import BinanceAPIException
from binance.enums import ORDER_TYPE_STOP_LOSS, ORDER_TYPE_LIMIT, ORDER_TYPE_MARKET, ORDER_TYPE_STOP_LOSS_LIMIT, \
    ORDER_TYPE_TAKE_PROFIT_LIMIT, ORDER_TYPE_TAKE_PROFIT
from typing import Optional, Dict, Any


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

    def check_status(self) -> str:
        """
        Check the status of the Binance client connection.

        Returns:
            str: A status message indicating whether the credentials are valid or not.
                  - 'Empty Credentials' if no client is initialized.
                  - 'Active' if the API credentials are valid.
                  - 'Invalid Credentials' if the API credentials are incorrect or expired.
        """

        if self.client is None:
            return 'Empty Credentials'
        try:
            self.client.get_account()
            return 'Active'
        except BinanceAPIException:
            return 'Invalid Credentials'

    def place_spot_order(self, order_type: str, trading_pair: str, side: str, quantity: float, price: Optional[float] = None, stop_price: Optional[float] = None, take_profit_price: Optional[float] = None, time_in_force: Optional[str] = None) -> Dict[str, Any]:
        """
        Places an order on Binance based on the given parameters.

        Args:
            order_type (str): The type of order (e.g., Market, Limit, Stop-Loss, etc.).
            trading_pair (str): The trading pair (e.g., BTCUSDT).
            side (str): Order side (BUY or SELL).
            quantity (float): Quantity to trade.
            price (Optional[float]): Price for limit orders.
            stop_price (Optional[float]): Stop price for stop-loss or take-profit orders.
            take_profit_price (Optional[float]): Take profit price for take-profit orders.
            time_in_force (Optional[str]): Time in force policy.

        Returns:
            Dict[str, Any]: Response from Binance API.
        """

        if order_type == "market":
            return self.client.order_market(
                symbol=trading_pair,
                side=side,
                type=ORDER_TYPE_MARKET,
                quantity=quantity
            )
        elif order_type == "limit":
            return self.client.order_limit(
                symbol=trading_pair,
                side=side,
                type=ORDER_TYPE_LIMIT,
                quantity=quantity,
                price=price,
                timeInForce=time_in_force
            )
        elif order_type == "stop-Loss":
            return self.client.create_order(
                symbol=trading_pair,
                side=side,
                type=ORDER_TYPE_STOP_LOSS,
                quantity=quantity,
                stopPrice=stop_price
            )
        elif order_type == "stop-loss limit":
            return self.client.create_order(
                symbol=trading_pair,
                side=side,
                type=ORDER_TYPE_STOP_LOSS_LIMIT,
                quantity=quantity,
                price=price,
                stopPrice=stop_price,
                timeInForce=time_in_force
            )
        elif order_type == "take-profit":
            return self.client.create_order(
                symbol=trading_pair,
                side=side,
                type=ORDER_TYPE_TAKE_PROFIT,
                quantity=quantity,
                stopPrice=take_profit_price
            )
        elif order_type == "take-profit limit":
            return self.client.create_order(
                symbol=trading_pair,
                side=side,
                type=ORDER_TYPE_TAKE_PROFIT_LIMIT,
                quantity=quantity,
                price=price,
                stopPrice=take_profit_price,
                timeInForce=time_in_force
            )
        elif order_type == "oco":
            return self.client.create_oco_order(
                symbol=trading_pair,
                side=side,
                quantity=quantity,
                price=price,
                stopPrice=stop_price
            )
        else:
            raise ValueError("Invalid order type")


    def place_spot_test_order(self, order_type: str, trading_pair: str, side: str, quantity: float, price: Optional[float] = None, stop_price: Optional[float] = None, take_profit_price: Optional[float] = None, time_in_force: Optional[str] = None) -> Dict[str, str]:
        """
        Same as place_spot_order but to test if the trade is possible.

        Returns:
            True if trade is possible, False if not.
        """
        try:
            if order_type == "market":
                res = self.client.create_test_order(
                    symbol=trading_pair,
                    side=side,
                    type=ORDER_TYPE_MARKET,
                    quantity=quantity
                )
            elif order_type == "limit":
                res = self.client.create_test_order(
                    symbol=trading_pair,
                    side=side,
                    type=ORDER_TYPE_LIMIT,
                    quantity=quantity,
                    price=price,
                    timeInForce=time_in_force
                )
            elif order_type == "stop-Loss":
                res = self.client.create_test_order(
                    symbol=trading_pair,
                    side=side,
                    type=ORDER_TYPE_STOP_LOSS,
                    quantity=quantity,
                    stopPrice=stop_price
                )
            elif order_type == "stop-loss limit":
                res = self.client.create_test_order(
                    symbol=trading_pair,
                    side=side,
                    type=ORDER_TYPE_STOP_LOSS_LIMIT,
                    quantity=quantity,
                    price=price,
                    stopPrice=stop_price,
                    timeInForce=time_in_force
                )
            elif order_type == "take-profit":
                res = self.client.create_test_order(
                    symbol=trading_pair,
                    side=side,
                    type=ORDER_TYPE_TAKE_PROFIT,
                    quantity=quantity,
                    stopPrice=take_profit_price
                )
            elif order_type == "take-profit limit":
                res = self.client.create_test_order(
                    symbol=trading_pair,
                    side=side,
                    type=ORDER_TYPE_TAKE_PROFIT_LIMIT,
                    quantity=quantity,
                    price=price,
                    stopPrice=take_profit_price,
                    timeInForce=time_in_force
                )
            elif order_type == "oco":
                res = self.client.create_test_order(
                    symbol=trading_pair,
                    side=side,
                    quantity=quantity,
                    price=price,
                    stopPrice=stop_price
                )
            else:
                return {"status": "error", "message": "Invalid order type"}
            if res == {}: # SUCCESS
                return {"status": "success", "message": ""}
            else:
                return {"status": "error", "message": res}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def fetch_market_price(self, pair: str) -> dict:
        """
        Fetch the current price of a given cryptocurrency trading pair.

        Args:
            pair (str): The trading pair symbol (e.g., 'BTCUSDT').

        Returns:
            dict: A dictionary containing the price or an error message.
        """
        try:
            price = self.client.get_symbol_ticker(symbol=pair)['price']
            return {"price": price}
        except BinanceAPIException as e:
            return {"error": str(e)}


    def get_spot_balance(self) -> dict:
        """
        Retrieve the user's spot balance, including free and locked amounts, along with current prices.

        Returns:
            dict: A dictionary containing spot balances, locked earn balances, staked balances, or an error message.
        """
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
                        fetched_price = self.fetch_market_price(asset['asset'] + 'USDT')
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
