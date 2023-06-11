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
                                    datetime_sell text NULL,
                                    coin_from float NOT NULL,
                                    coin_to float NOT NULL,
                                    bet_value float NOT NULL,
                                    buy_price float NULL,
                                    sell_price float NULL,
                                    profit float NULL,
                                    strategy text NOT NULL,
                                    fees text NULL,
                                    status text NOT NULL
                                );"""
    cursor.execute(sql_create_trading_history_table_query)  # execute query

    # # INSERT DEFAULT PARAMS
    # insert_default_query = """INSERT INTO user_conf(exchange_choice,backend_server_ip,backend_server_port,backend_server_socket_address)
    #               VALUES("Binance","http://127.0.0.1",8000, "http://127.0.0.1:8000/");"""
    # cursor.execute(insert_default_query)
    conn.commit() # Save the changes
    cursor.close() # Close the cursor and the connection
    conn.close()
    print("query_handler :: Database created successfully.")
    return 0


def add_trade_to_db():
    conn = sqlite3.connect('backend/db/backend_db.db')  # Create/Connect to the SQLite database
    cursor = conn.cursor()  # Create a cursor object to execute SQL commands

    # # INSERT PARAMS
    insert_default_query = """INSERT INTO user_conf(exchange_choice,backend_server_ip,backend_server_port,backend_server_socket_address)
                  VALUES("Binance","http://127.0.0.1",8000, "http://127.0.0.1:8000/");"""
    cursor.execute(insert_default_query)
    conn.commit()  # Save the changes
    cursor.close()  # Close the cursor and the connection
    conn.close()


def fetch_trading_history(date_from=None, date_to=None):
    conn = sqlite3.connect('frontend/db/frontend_db.db')
    cursor = conn.cursor()
    # Fetch all fields from the configuration table
    cursor.execute("SELECT * FROM trading_history")
    rows = cursor.fetchall()
    # print(rows)
    cursor.close()
    conn.close()
    return rows
