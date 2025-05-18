import sqlite3
import os
from streamlit import cache_resource
from dotenv import load_dotenv


"""
This script uses the sqlite3 module to connect to an SQLite database file called frontend.db. 
It creates a table named "user_configuration" with the specified fields: 
exchange, llm_source, llm_type, llm_name, backend_server_ip, backend_server_port and backend_server_secure. 
The table has an additional primary key field called id for unique identification of each record.
"""

load_dotenv('frontend/config/config.env')
DB_PATH = os.getenv("FRONTEND_DB_PATH")

def db_init() -> int:
    # Check if the database file already exists
    if os.path.exists(DB_PATH):
        print("db_connector :: Database already exists.")
        return 0

    conn = sqlite3.connect(DB_PATH)  # Create/Connect to the SQLite database

    cursor = conn.cursor()  # Create a cursor object to execute SQL commands
    # Create Table that holds the User Preferences/Configurations
    sql_create_conf_table_query = """CREATE TABLE IF NOT EXISTS user_configuration (
                                    id integer PRIMARY KEY,
                                    exchange text NOT NULL,
                                    llm_source text,
                                    llm_type text,
                                    llm_name text,
                                    backend_server_ip text NOT NULL,
                                    backend_server_port integer NOT NULL,
                                    backend_server_secure integer NOT NULL
                                );"""
    cursor.execute(sql_create_conf_table_query)  # execute query

    # INSERT DEFAULT PARAMS
    insert_default_query = """INSERT INTO user_configuration(exchange, backend_server_ip,backend_server_port,backend_server_secure)
                  VALUES("Binance", "127.0.0.1", 8000, 0);"""
    cursor.execute(insert_default_query)
    conn.commit() # Save the changes
    # Close the cursor and the connection
    cursor.close()
    conn.close()
    print("db_connector :: Database created successfully.")
    return 0


@cache_resource
def fetch_fields() -> dict:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Fetch all fields from the configuration table
    cursor.execute("SELECT * FROM user_configuration")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    res = {"exchange": rows[0][1],
           "llm_source": rows[0][2],
           "llm_type": rows[0][3],
           "llm_name": rows[0][4],
           "backend_server_ip": rows[0][5],
           "backend_server_port": rows[0][6],
           "backend_server_secure": rows[0][7]
           }
    return res


@cache_resource
def fetch_llm_config() -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Fetch all fields from the configuration table
    cursor.execute("SELECT llm_source, llm_type, llm_name FROM user_configuration")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    if rows[0][0] and rows[0][1] and rows[0][2]:
        return {"llm_source": rows[0][0], "llm_type": rows[0][1], "llm_name": rows[0][2]}
    else:
        return None


def update_fields(exchange: str = None, llm_source: str = None, llm_type: str = None, llm_name: str = None, backend_server_ip: str = None,
                  backend_server_port: int = None, backend_server_secure: int = None) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Update the fields if arguments are not None
    cursor.execute("""UPDATE user_configuration SET
                      exchange = COALESCE(?, exchange),
                      llm_source = COALESCE(?, llm_source),
                      llm_type = COALESCE(?, llm_type),
                      llm_name = COALESCE(?, llm_name),
                      backend_server_ip = COALESCE(?, backend_server_ip),
                      backend_server_port = COALESCE(?, backend_server_port),
                      backend_server_secure = COALESCE(?, backend_server_secure)""",
                   (exchange, llm_source, llm_type, llm_name, backend_server_ip,
                    backend_server_port, backend_server_secure))
    conn.commit()
    cursor.close()
    conn.close()
    fetch_fields.clear()  # Clear cache in order to return updated results
    print("db_connector :: Fields updated successfully.")
    return 0
