from plotly.graph_objs import Figure
from streamlit import sidebar, spinner, dataframe as st_dataframe, plotly_chart, warning, error, expander, write, tabs, info
from frontend.src.library.analytics_helper.client import fetch_price_history
from frontend.src.library.history_helper.client import update_trading_history, fetch_trading_history
from pandas import DataFrame, to_datetime, isnull, to_numeric, Series
from plotly.graph_objects import Figure, Scatter, Pie
from frontend.src.library.analytics_helper.plots import price_history_plot
from frontend.src.library.crypto_dictionary_assistant import get_crypto_coin_dict_inv
from plotly.subplots import make_subplots
from collections import defaultdict
from typing import Dict, List


def sidebar_update_history():
    if sidebar.button('Update Order Statuses', icon=":material/update:", use_container_width=True):
        with spinner('Fetching latest Strategy History Status'):
            res = update_trading_history()
            if res.status_code == 200:
                if "success" in res.json():
                    sidebar.success(res.json())
                else:
                    sidebar.error(res.json())
            else:
                sidebar.error(res.json())

def highlight_profit(val):
    color = 'grey'  # default color for zero or null
    if val > 0:
        color = 'green'
    elif val < 0:
        color = 'red'
    return f'background-color: {color}'


def trading_history_table():
    orders = fetch_trading_history()
    if orders is None:
        return None
    else:
        df = DataFrame(columns=['Exchange', 'DateTime', 'Order Id', 'Quote Asset', 'Base Asset', 'Base Quantity',
                                            'Quote Quantity', 'Side', 'Type', 'Status',
                                            'TiF', 'Commission', 'Commission Asset', 'STPM'],
                                   data=orders)

        df["DateTime"] = to_numeric(df["DateTime"], errors="coerce")
        df["DateTime"] = to_datetime(df["DateTime"], unit="ms")  # Use 's' if timestamps are in seconds
        df["DateTime"] = df["DateTime"].dt.strftime("%Y-%m-%d %H:%M:%S")

        return df.sort_values(by='DateTime', ascending=False)


def get_status_barplot(status_series: Series):
    BINANCE_ORDER_STATUS_COLORS = {
        'NEW': '#ADD8E6',              # Light Blue - Order is new
        'PARTIALLY_FILLED': '#FFD700', # Gold - Order is partially filled
        'FILLED': '#0073CF',           # Deep Blue - Order fully executed
        'CANCELED': '#E34234',         # Red - Order was canceled
        'PENDING_CANCEL': '#FF8C00',   # Dark Orange - Order is pending cancellation
        'REJECTED': '#8B0000',         # Dark Red - Order was rejected
        'EXPIRED': '#808080',          # Gray - Order expired
        'EXPIRED_IN_MATCH': '#A9A9A9'  # Dark Gray - Order expired while being matched
    }
    COINBASE_ORDER_STATUS_COLORS = {
        'pending': '#ADD8E6',  # Light Blue - Order is pending
        'open': '#FFD700',  # Gold - Order is open but not filled
        'active': '#FFA500',  # Orange - Order is currently live
        'done': '#0073CF',  # Deep Blue - Order fully executed
        'settled': '#50C878',  # Emerald Green - Order settled
        'canceled': '#E34234',  # Red - Order was canceled
        'expired': '#808080'  # Gray - Order expired
    }
    KRAKEN_ORDER_STATUS_COLORS = {
        'pending': '#ADD8E6',  # Light Blue - Order is pending
        'open': '#FFD700',  # Gold - Order is open but not filled
        'closed': '#0073CF',  # Deep Blue - Order fully executed
        'canceled': '#E34234',  # Red - Order was canceled
        'expired': '#808080'  # Gray - Order expired
    }

    status_counts = status_series.value_counts()
    fig = Figure(data=[Pie(labels=status_counts.index, values=status_counts.values, hole=0.5, textinfo='value+percent')])
    fig.update_traces(marker=dict(colors=[BINANCE_ORDER_STATUS_COLORS[status] for status in status_counts.index]))
    plotly_chart(fig, config=dict(displayModeBar=False))


def get_trading_history_line_plot(trade_df: DataFrame) -> Figure | None:

    if trade_df.shape[0] > 5:
        warning("💡 A maximum of **5 Trades** can be plotted concurrently!")  # trade_df = trade_df[0:4]
        return None
    if len(list(trade_df['Base Asset'].unique())) > 2:
        warning("⚠️ A maximum of **2** different base Assets can be plotted concurrently!")  # trade_df = trade_df[0:4]
        return None

    trade_df['DateTime'] = to_datetime(trade_df['DateTime']).dt.round('30min')
    trade_df['DateTime [Sell]'] = to_datetime(trade_df['DateTime [Sell]']).dt.round('30min')
    coins_list = list(trade_df['Base Asset'].unique())
    more_that_one_coins_flag = False
    if len(coins_list) > 1:
        coins_list = coins_list[0:2]
        more_that_one_coins_flag = True

    # Get Historic Prices
    price_hist_df = fetch_price_history("binance", f"{coins_list[0]}USDT", '30m', 500)
    col_name = coins_list[0] + ' Price'
    price_hist_df[col_name] = price_hist_df['Close Price']
    if more_that_one_coins_flag:
        price_hist_df_tmp = fetch_price_history("binance", f"{coins_list[0]}USDT", '30m', 500)
        col_name1 = coins_list[1] + ' Price'
        price_hist_df[col_name1] = price_hist_df_tmp['Close Price']

    # Convert datetime columns to pandas DateTime objects
    price_hist_df['DateTime'] = to_datetime(price_hist_df['DateTime']).dt.round('30min')

    # Support a maximum of 4 concurrent plots
    # Different marker shape for each buy/sell order
    status_symbols = [100, 106, 102, 101, 117] # open circle, triangle-down, diamond, square, star
    # status_symbols = {'Greedy': 106, 'Oracle': 206} # Create a dictionary to map status values to numerical symbols

    # Create the figure
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    # Add the line plot
    fig.add_trace(Scatter(
        x=price_hist_df['DateTime'],
        y=price_hist_df[col_name],
        mode='lines',
        name=coins_list[0]+' Price'
    ))

    if more_that_one_coins_flag:
        fig.add_trace(Scatter(
            x=price_hist_df['DateTime'],
            y=price_hist_df[col_name1],
            mode='lines',
            name=coins_list[1]+' Price',
        ), secondary_y=True,)

    # Iterate over each buy/sell pair and add a separate scatter trace
    for i, pair in trade_df.iterrows():
        buy_dt = pair['DateTime']
        sell_dt = pair['DateTime [Sell]']
        status = pair['Strategy']
        price_col = pair['to_asset'] + ' Price'

        if pair['to_asset'] == coins_list[0]:
            secondary_plot = False
        else:
            secondary_plot = True

        if len(price_hist_df[price_hist_df['DateTime'] == buy_dt][price_col].values) < 1:
            error('Plot for old dates is not supported yet!')
            return None
        # Add scatter trace for the buy point
        fig.add_trace(Scatter(
            x=[buy_dt],
            y=[price_hist_df[price_hist_df['DateTime'] == buy_dt][price_col].values[0]],
            mode='markers',
            marker=dict(color='green', size=16, symbol=status_symbols[i]),
            name=f'Buy {i+1}: {status}',
            text=f'Buy Date: {buy_dt}<br>Buy Price: {price_hist_df[price_hist_df["DateTime"] == buy_dt][price_col].values[0]}',
            hoverinfo='text'
        ), secondary_y=secondary_plot)

        if not isnull(sell_dt):  # 'NaT'
            # Add scatter trace for the sell point
            fig.add_trace(Scatter(
                x=[sell_dt],
                y=[price_hist_df[price_hist_df['DateTime'] == sell_dt][price_col].values[0]], # add [] around y, if it doesnt work
                mode='markers',
                marker=dict(color='red', size=16, symbol=status_symbols[i]),
                name=f'Sell {i+1}: {status}',
                text=f'Sell Date: {sell_dt}<br>Sell Price: {price_hist_df[price_hist_df["DateTime"] == sell_dt][price_col].values[0]}',
                hoverinfo='text'
            ), secondary_y=secondary_plot)

    # Set plot layout
    fig.update_layout(
        title= str(coins_list) + ' Price with Buy/Sell Points',
        xaxis_title='Date',
        yaxis_title='Price'
    )

    return fig


def trade_history_instructions():
    with expander("Trading Table information", expanded=False, icon=":material/contact_support:"):
        tab0, tab1 = tabs(["Order Statuses", "Order Plots"])
        with tab0:
            data = {
                "Explanation": [
                    "Order is created but not yet filled",
                    "Order is partially filled but not yet complete",
                    "Order is fully executed",
                    "Order is canceled before execution",
                    "Order is expired due to time constraints",
                    "Order is rejected by the exchange",
                    "Order is in the process of being canceled",
                    "Order is fully settled and funds are transferred",
                    "Order is currently active and can be matched",
                    "Order expired while being matched"
                ],
                "Binance Status": [
                    "NEW",
                    "PARTIALLY_FILLED",
                    "FILLED",
                    "CANCELED",
                    "EXPIRED",
                    "REJECTED",
                    "PENDING_CANCEL",
                    "FILLED",
                    "NEW",
                    "EXPIRED_IN_MATCH"
                ],
                "Kraken Status": [
                    "pending",
                    "open",
                    "closed",
                    "canceled",
                    "expired",
                    "rejected",
                    "canceled (if confirmed)",
                    "closed",
                    "open",
                    "Not applicable"
                ],
                "Coinbase Status": [
                    "pending",
                    "open",
                    "done (filled)",
                    "canceled",
                    "expired",
                    "Not explicitly listed",
                    "Not explicitly listed",
                    "settled",
                    "active",
                    "Not applicable"
                ]
            }
            statuses_df = DataFrame(data)
            write("**Order Statuses Comparison (Binance, Kraken, Coinbase)**:")
            st_dataframe(statuses_df, use_container_width=True, hide_index=True)
            info("💡 In order to update the status and get the latest information about an **open order**, click on the update button in the sidebar. This will initiate a function that will fetch the order status from the exchange API.")
        with tab1:
            write("TBA")
