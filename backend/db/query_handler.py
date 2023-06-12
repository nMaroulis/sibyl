import sqlite3
import os


"""
This script uses the sqlite3 module to connect to an SQLite database file called backend_db.db. 
It creates a table named "trading_history" with the specified fields: 
"""

def db_init():
    # Check if the database file already exists
    if os.path.exists('backend/db/backend_db.db'):
        print("query_handler :: Database already exists.")
        return 0

    conn = sqlite3.connect('backend/db/backend_db.db')  # Create/Connect to the SQLite database
    cursor = conn.cursor()  # Create a cursor object to execute SQL commands

    sql_create_trading_history_table_query = """CREATE TABLE IF NOT EXISTS trading_history (
                                    id integer PRIMARY KEY,
                                    exchange text NOT NULL,
                                    datetime_buy text NOT NULL,
                                    asset_from float NOT NULL,
                                    asset_to float NOT NULL,
                                    asset_from_buy_value float NOT NULL,
                                    asset_to_buy_quantity float NOT NULL,
                                    datetime_sell text NULL,
                                    asset_from_sell_value float NULL,
                                    asset_to_sell_value float NULL,
                                    profit float NULL,
                                    strategy text NOT NULL,
                                    fees text NULL,
                                    status text NOT NULL
                                );"""
    cursor.execute(sql_create_trading_history_table_query)  # execute query
    conn.commit() # Save the changes
    cursor.close() # Close the cursor and the connection
    conn.close()
    print("backend :: db :: query_handler :: Database created successfully.")
    return 0


def add_trade_to_db(exchange='binance', datetime_buy='', asset_from='USDT', asset_to="BTC",
                    asset_from_buy_value=1.0, asset_to_buy_quantity=1.0, datetime_sell=None, asset_from_sell_value=None, asset_to_sell_value=None, profit=None, strategy='greedy', fees=0, status='active'):
    conn = sqlite3.connect('backend/db/backend_db.db')  # Create/Connect to the SQLite database
    cursor = conn.cursor()  # Create a cursor object to execute SQL commands

    # # INSERT PARAMS
    cursor.execute("""INSERT INTO trading_history(exchange,datetime_buy,asset_from, asset_to, asset_from_buy_value, asset_to_buy_quantity, strategy, status)
                  VALUES(?,?,?,?,?,?,?,?)""",(exchange, datetime_buy, asset_from, asset_to, asset_from_buy_value, asset_to_buy_quantity, strategy, status))
    # cursor.execute(insert_default_query)
    conn.commit()  # Save the changes
    cursor.close()  # Close the cursor and the connection
    conn.close()
    print("backend :: db :: query_handler :: add_trade_to_db :: Database Insert successfully.")
    return 0

def fetch_trading_history(date_from=None, date_to=None):
    conn = sqlite3.connect('backend/db/backend_db.db')
    cursor = conn.cursor()
    # Fetch all fields from the configuration table
    cursor.execute("SELECT * FROM trading_history")
    rows = cursor.fetchall()
    # print(rows)
    cursor.close()
    conn.close()
    return rows
