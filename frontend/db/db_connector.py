import sqlite3
import os
from streamlit import cache_resource

"""
This script uses the sqlite3 module to connect to an SQLite database file called database.db. 
It creates a table named "configuration" with the specified fields: 
exchange_choice, nlp_model_choice, backend_server_ip, backend_server_port, and backend_server_socket_address. 
The table has an additional primary key field called id for unique identification of each record.
"""


def db_init():
    # Check if the database file already exists
    if os.path.exists('frontend/db/frontend_db.db'):
        print("db_connector :: Database already exists.")
        return 0

    conn = sqlite3.connect('frontend/db/frontend_db.db')  # Create/Connect to the SQLite database

    cursor = conn.cursor()  # Create a cursor object to execute SQL commands
    sql_create_conf_table_query = """CREATE TABLE IF NOT EXISTS user_conf (
                                    id integer PRIMARY KEY,
                                    exchange_choice text NOT NULL,
                                    nlp_model_choice text,
                                    backend_server_ip text NOT NULL,
                                    backend_server_port integer NOT NULL,
                                    backend_server_socket_address text NOT NULL
                                );"""
    cursor.execute(sql_create_conf_table_query)  # execute query

    # INSERT DEFAULT PARAMS
    insert_default_query = """INSERT INTO user_conf(exchange_choice,backend_server_ip,backend_server_port,backend_server_socket_address)
                  VALUES("binance","http://127.0.0.1:",8000, "http://127.0.0.1:8000");"""
    cursor.execute(insert_default_query)
    conn.commit() # Save the changes
    # Close the cursor and the connection
    cursor.close()
    conn.close()
    print("db_connector :: Database created successfully.")
    return 0

@cache_resource
def fetch_fields():
    conn = sqlite3.connect('frontend/db/frontend_db.db')
    cursor = conn.cursor()
    # Fetch all fields from the configuration table
    cursor.execute("SELECT * FROM user_conf")
    rows = cursor.fetchall()
    print(rows)
    cursor.close()
    conn.close()
    return rows


def update_fields(exchange_choice=None, nlp_model_choice=None, backend_server_ip=None,
                  backend_server_port=None, backend_server_socket_address=None):
    conn = sqlite3.connect('frontend/db/frontend_db.db')
    cursor = conn.cursor()
    # Update the fields if arguments are not None
    if exchange_choice is not None:
        cursor.execute("UPDATE user_conf SET exchange_choice = ?", (exchange_choice,))
    if nlp_model_choice is not None:
        cursor.execute("UPDATE user_conf SET nlp_model_choice = ?", (nlp_model_choice,))
    if backend_server_ip is not None:
        cursor.execute("UPDATE user_conf SET backend_server_ip = ?", (backend_server_ip,))
    if backend_server_port is not None:
        cursor.execute("UPDATE user_conf SET backend_server_port = ?", (backend_server_port,))
    if backend_server_socket_address is not None:
        cursor.execute("UPDATE user_conf SET backend_server_socket_address = ?",
                       (backend_server_socket_address,))
    conn.commit()
    cursor.close()
    conn.close()
    fetch_fields.clear()  # Clear cache in order to return updated results
    print("db_connector :: Fields updated successfully.")
    return 0
