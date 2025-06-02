import streamlit as st
from frontend.src.utils.wallet_helper.client import fetch_account_spot
from frontend.src.utils.spot_trade_helper.client import post_spot_trade, fetch_asset_market_price
from typing import Dict, Any


def get_account_balance(quote_asset: str, quantity: float, market_price: float) -> None:
    """
    Checks the user's account balance for a given asset and compares it with the specified quantity.
    Displays warnings or success messages based on the available balance.

    Args:
        quote_asset (str): The asset symbol to check (e.g., "BTC", "ETH").
        quantity (float): The amount of the asset to compare against the balance.

    Returns:
        None
    """

    account_balance_key: str = f"{st.session_state['trade_exchange_api'].lower().replace(" ", "_")}_account_balance"
    if account_balance_key not in st.session_state:  # if account balance calculated
        with st.spinner("Fetching account balance..."):
            account_balance: Dict[str, Any] = fetch_account_spot(st.session_state['trade_exchange_api'], None)
            st.session_state[account_balance_key] = {asset: price["free"] for asset, price in
                                                     account_balance["spot_balances"].items()}

    if quote_asset in st.session_state[account_balance_key].keys():
        if market_price is not None:
            if quantity*market_price > st.session_state[account_balance_key][quote_asset]:
                st.error(
                    f"Warning: The quantity of **{quantity*market_price} {quote_asset}** is **larger** than your balance of **{st.session_state[account_balance_key][quote_asset]} {quote_asset}**. This order will fail.",
                    icon=":material/counter_5:")
            else:
                st.success(
                    f"The quantity of **{quantity*market_price} {quote_asset}** is **lower** than your balance of **{st.session_state[account_balance_key][quote_asset]} {quote_asset}**.",
                    icon=":material/counter_5:")
        else:
            st.info( f"Your account balance is **{st.session_state[account_balance_key][quote_asset]} {quote_asset}**, don't choose a quantity larger than your balance because the **order will fail**.", icon=":material/counter_5:")
    else:
        st.error(f"Warning: No available **{quote_asset}** in your account. This order will fail.",
                   icon=":material/counter_5:")


def get_pair_market_price(quote_asset: str, base_asset: str, quantity: float, min_trade_value: float) -> int | None:

    if st.session_state['trade_exchange_api'] == "Coinbase" or st.session_state[
        'trade_exchange_api'] == "Coinbase Sandbox":
        trading_pair = f"{base_asset}-{quote_asset}"
    else:
        trading_pair = base_asset + quote_asset

    market_price = fetch_asset_market_price(st.session_state['trade_exchange_api'], trading_pair)
    st.info(f"**Trading pair**: {trading_pair}", icon=":material/counter_1:")

    if market_price:
        st.info(f"**{base_asset} Current price**: {market_price} {quote_asset}", icon=":material/counter_2:")
        st.info(f"You'll trade **{round(quantity * market_price, 4)} {quote_asset}** for **{quantity} {base_asset}**", icon=":material/counter_3:")
        # min_trade_limit = fetch_minimum_trade_value(st.session_state['trade_exchange_api'], trading_pair)
        if quantity * market_price >= min_trade_value:
            st.success("The **minimum trade value limit** of **" + str(
                min_trade_value) + "** for the " + trading_pair + " pair is satisfied!", icon=":material/counter_4:")
        else:
            st.error("The **minimum trade value limit** of **" + str(
                min_trade_value) + "** for the " + trading_pair + " pair is NOT satisfied.", icon=":material/counter_4:")
    else:
        st.warning("**Failed** to fetch current trading pair **market price**.", icon=":material/counter_2:")
        st.warning("**Failed** to calculate the **quantity** of **Quote asset** necessary for this order..", icon=":material/counter_3:")
        st.warning(f"**Failed** the **minimum trade quote limit** for this order is {min_trade_value} cannot calculate feasibility based on market price..", icon=":material/counter_4:")

    return market_price


def submit_order(order_type: str, quote_asset: str, base_asset: str, side: str, quantity: float, price: float, stop_price: float, take_profit_price: float, time_in_force: str) -> None:

    with st.spinner("Sending Test Order..."):
        test_res = post_spot_trade(True, st.session_state['trade_exchange_api'], order_type, quote_asset, base_asset,
                                   side, quantity,
                                   price, stop_price, take_profit_price, time_in_force)
    if test_res is None or "status" not in test_res.keys():
        st.error("Something went wrong when parsing the server response.", icon=":material/warning:")
    else:
        if test_res["status"] == "success":
            st.success("Test Order was **validated**, your Trade Order being placed right now...",
                       icon=":material/task_alt:")
            with st.spinner("Placing Order..."):
                res = post_spot_trade(False, st.session_state['trade_exchange_api'], order_type, quote_asset,
                                      base_asset, side,
                                      quantity,
                                      price, stop_price, take_profit_price, time_in_force)
                if res is None or "status" not in res.keys():
                    st.error("Something went wrong when parsing the server response.", icon=":material/warning:")
                else:
                    if res["status"] == "success":
                        st.success(
                            "Order was **placed** successfully and added to the TradeHistory DB, please find API response below.",
                            icon=":material/task_alt:")
                        st.link_button("You can find the SPOT order in the Trading History tab.",
                                       "http://localhost:8501/trading_report ", type="secondary",
                                       icon=":material/youtube_searched_for:")
                        st.write(f"Below is the response message returned by the {st.session_state['trade_exchange_api']} API.")
                        st.json(res["message"])
                        st.toast("Your Trade Order has been placed successfully.", icon="✅")
                    else:
                        st.warning(f"Order is **invalid**. Error message {res["message"]}", icon=":material/warning:")
        else:
            st.error(f"Test Order is **invalid**. Error message {test_res["message"]}", icon=":material/warning:")
