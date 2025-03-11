import sqlite3
import os
from dotenv import load_dotenv


"""
This script uses the sqlite3 module to connect to an SQLite database file called trade_history.db. 
It creates a table named "trading_history" with the specified fields
"""

class TradeHistoryDBClient:

    load_dotenv('database/db_paths.env')
    DB_PATH = os.getenv("TRADE_HISTORY_DB_PATH")


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
                                        timestamp bigint NOT NULL,
                                        order_id text NOT NULL,
                                        quote_asset text NOT NULL,
                                        base_asset text NOT NULL,
                                        base_quantity float NOT NULL,
                                        quote_quantity float NOT NULL,
                                        side text NOT NULL,
                                        order_type text NOT NULL,
                                        order_status text NOT NULL,
                                        time_in_force text NOT NULL,
                                        commission float NULL,
                                        commission_asset text NULL,
                                        self_trade_prevention_mode text NULL
                                    );"""
        cursor.execute(sql_create_trading_history_table_query)  # execute query
        conn.commit()
        cursor.close()
        conn.close()
        print("backend :: db :: trade_history_db_client :: Database created successfully.")
        return 0


    @classmethod
    def add_trade_to_db(cls, exchange: str, timestamp: int, order_id: str, quote_asset: str, base_asset: str,
                        base_quantity: float, quote_quantity: float, side: str, order_type: str, order_status: str, time_in_force: str, commission: float = None, commission_asset: str = None, self_trade_prevention_mode: str = None):
        conn = sqlite3.connect(cls.DB_PATH)  # Create/Connect to the SQLite database
        cursor = conn.cursor()  # Create a cursor object to execute SQL commands

        # # INSERT PARAMS
        cursor.execute("""INSERT INTO trading_history(exchange, timestamp, order_id, quote_asset, base_asset, 
        base_quantity, quote_quantity, side, order_type, order_status, time_in_force, commission, commission_asset,
        self_trade_prevention_mode) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (exchange, timestamp, order_id, quote_asset, base_asset, base_quantity, quote_quantity,
                        side, order_type, order_status, time_in_force, commission,
                        commission_asset, self_trade_prevention_mode))
        # cursor.execute(insert_default_query)
        conn.commit()  # Save the changes
        cursor.close()  # Close the cursor and the connection
        conn.close()
        print("database :: trade_history_db_client :: add_trade_to_db :: Database Insert successfully.")
        return 0


    @classmethod
    def fetch_trading_history(cls, date_from: str = None, date_to: str = None):
        conn = sqlite3.connect(cls.DB_PATH)
        cursor = conn.cursor()

        cursor.execute(f"SELECT exchange, timestamp, order_id, quote_asset, base_asset, base_quantity, quote_quantity, side, order_type, order_status, time_in_force, commission, commission_asset, self_trade_prevention_mode FROM trading_history")
        rows = cursor.fetchall()
        # print(rows)
        cursor.close()
        conn.close()
        return rows
    #
    #
    # @classmethod
    # def update_strategy_status(cls, sell_id=None, asset_from='USDT', asset_to='BTC', new_status='active', time_sold='pending'):
    #     conn = sqlite3.connect(cls.DB_PATH)
    #     cursor = conn.cursor()
    #     update_query = """
    #         UPDATE trading_history
    #         SET status = ?, datetime_sell = ?
    #         WHERE orderid_sell = ? AND asset_from = ? AND asset_to = ?;
    #     """
    #     query_success = True
    #     try:
    #         cursor.execute(update_query, (new_status, time_sold, sell_id, asset_from, asset_to))
    #         conn.commit()
    #     except:
    #         query_success = False
    #
    #     cursor.close()
    #     conn.close()
    #     return query_success
