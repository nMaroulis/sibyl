import streamlit as st
from frontend.src.library.settings_helper.client import fetch_apis_status


def api_status_check():
    if "api_status_check" not in st.session_state:
        status_json = fetch_apis_status("exchanges")
        status_list = list(status_json.values())
        st.session_state["binance_api_status"] = status_list[0]
        st.session_state["binance_testnet_api_status"] = status_list[1]
        st.session_state["kraken_api_status"] = status_list[2]
        st.session_state["coinbase_api_status"] = status_list[3]

        st.session_state["available_exchange_apis"] = []
        if st.session_state["binance_api_status"] == "Active":
            st.session_state["available_exchange_apis"].append("Binance")
        if st.session_state["binance_testnet_api_status"] == "Active":
            st.session_state["available_exchange_apis"].append("Binance Testnet")
        if st.session_state["kraken_api_status"] == "Active":
            st.session_state["available_exchange_apis"].append("Kraken")
        if st.session_state["coinbase_api_status"] == "Active":
            st.session_state["available_exchange_apis"].append("Coinbase")

