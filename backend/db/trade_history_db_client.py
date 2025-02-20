import sqlite3
import os


"""
This script uses the sqlite3 module to connect to an SQLite database file called trade_history.db. 
It creates a table named "trading_history" with the specified fields
"""

class TradeHistoryDBClient:

    DB_PATH = 'backend/db/trade_history.db'


    @classmethod
    def db_init(cls):
        # Check if the database file already exists
        if os.path.exists(cls.DB_PATH):
            print("trade_history_db_client :: Database already exists.")
            return 0

        conn = sqlite3.connect(cls.DB_PATH)  # Create/Connect to the SQLite database
        cursor = conn.cursor()  # Create a cursor object to execute SQL commands

        sql_create_trading_history_table_query = """CREATE TABLE IF NOT EXISTS trading_history (
                                        id integer PRIMARY KEY,
                                        exchange text NOT NULL,
                                        datetime_buy text NOT NULL,
                                        orderid_buy text NOT NULL,
                                        asset_from float NOT NULL,
                                        asset_to float NOT NULL,
                                        asset_from_amount float NOT NULL,
                                        asset_to_quantity float NOT NULL,
                                        asset_to_price float NOT NULL,
                                        datetime_sell text NULL,
                                        orderid_sell text NULL,
                                        asset_to_sell_price float NULL,
                                        profit float NULL,
                                        order_type text NULL,
                                        strategy text NOT NULL,
                                        fees text NULL,
                                        status text NOT NULL
                                    );"""
        cursor.execute(sql_create_trading_history_table_query)  # execute query
        conn.commit()  # Save the changes
        cursor.close()  # Close the cursor and the connection
        conn.close()
        print("backend :: db :: trade_history_db_client :: Database created successfully.")
        return 0


    @classmethod
    def add_trade_to_db(cls, exchange: str = 'binance', datetime_buy: str = '', orderid_buy: str = '', asset_from: str = 'USDT', asset_to: str = "BTC",
                        asset_from_amount: float = 1.0, asset_to_quantity: float = 1.0, asset_to_price: float = 0.0, datetime_sell=None, orderid_sell='', asset_to_sell_price=None, profit=None, order_type='trade', strategy='greedy', fees=0, status='active'):
        conn = sqlite3.connect(cls.DB_PATH)  # Create/Connect to the SQLite database
        cursor = conn.cursor()  # Create a cursor object to execute SQL commands

        # # INSERT PARAMS
        cursor.execute("""INSERT INTO trading_history(exchange, datetime_buy, orderid_buy, asset_from, asset_to, 
        asset_from_amount, asset_to_quantity, asset_to_price, datetime_sell, orderid_sell, asset_to_sell_price, order_type,
        strategy, status)
                      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (exchange, datetime_buy, orderid_buy, asset_from, asset_to,
                                                   asset_from_amount, asset_to_quantity, asset_to_price, datetime_sell,
                                                   orderid_sell, asset_to_sell_price, order_type, strategy, status))
        # cursor.execute(insert_default_query)
        conn.commit()  # Save the changes
        cursor.close()  # Close the cursor and the connection
        conn.close()
        print("backend :: db :: trade_history_db_client :: add_trade_to_db :: Database Insert successfully.")
        return 0


    @classmethod
    def fetch_trading_history(cls, date_from: str = None, date_to: str = None, status: str = 'active'):
        conn = sqlite3.connect(cls.DB_PATH)
        cursor = conn.cursor()

        if status == 'all':
            cursor.execute(f"SELECT exchange, datetime_buy, orderid_buy, asset_from, asset_to, asset_from_amount, "
                           f"asset_to_quantity, asset_to_price, datetime_sell, orderid_sell, asset_to_sell_price, "
                           f"order_type, strategy, status FROM trading_history")
        else:
            # Fetch all fields from the configuration table
            cursor.execute(f"SELECT exchange, datetime_buy, orderid_buy, asset_from, asset_to, asset_from_amount, "
                           f"asset_to_quantity, asset_to_price, datetime_sell, orderid_sell, asset_to_sell_price, "
                           f"order_type, strategy, status FROM trading_history WHERE status = '{status}'")
        rows = cursor.fetchall()
        # print(rows)
        cursor.close()
        conn.close()
        return rows


    @classmethod
    def update_strategy_status(cls, sell_id=None, asset_from='USDT', asset_to='BTC', new_status='active', time_sold='pending'):
        conn = sqlite3.connect(cls.DB_PATH)
        cursor = conn.cursor()
        update_query = """
            UPDATE trading_history
            SET status = ?, datetime_sell = ?
            WHERE orderid_sell = ? AND asset_from = ? AND asset_to = ?;
        """
        query_success = True
        try:
            cursor.execute(update_query, (new_status, time_sold, sell_id, asset_from, asset_to))
            conn.commit()
        except:
            query_success = False

        cursor.close()
        conn.close()
        return query_success
