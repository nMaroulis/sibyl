import streamlit as st
import time
import plotly.graph_objs as go
import numpy as np
import pandas as pd
from frontend.src.library.strategy_helper.client import get_strategy_logs


# Function to generate a random initial DataFrame
def generate_random_df(size=50):
    timestamps = np.arange(size)
    prices = np.cumsum(np.random.randn(size)) + 100  # Simulated price movement
    orders = np.random.choice(["BUY", "SELL", "HOLD"], size=size)
    return pd.DataFrame({"timestamp": timestamps, "price": prices, "order": orders})

def update_logs(strategy_id: str, last_timestamp: int):

    logs = get_strategy_logs(strategy_id, last_timestamp)  # df_to_show["strategy_id"].iloc[0])
    if logs is None or len(logs) == 0:
        return None

    logs_df = pd.DataFrame(logs)
    logs_df['timestamp'] = pd.to_datetime(logs_df['timestamp'], unit='ms')
    return logs_df


@st.fragment()
def real_time_strategy_plot(df: pd.DataFrame, strategy_id: str):
    # Create a placeholder for the Plotly chart
    chart = st.empty()
    # Initialize figure
    fig = go.Figure()

    # Add initial traces
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["price"], mode='lines', name='Price'))
    fig.add_trace(go.Scatter(x=df[df["order"] == "BUY"]["timestamp"], y=df[df["order"] == "BUY"]["price"], mode='markers', marker=dict(color='green', size=10), name='BUY'))
    fig.add_trace(go.Scatter(x=df[df["order"] == "SELL"]["timestamp"], y=df[df["order"] == "SELL"]["price"], mode='markers', marker=dict(color='red', size=10), name='SELL'))

    # Display the empty chart
    chart.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

    # Real-time update loop
    while True:
        upd_logs = update_logs(strategy_id, int(df['timestamp'].iloc[-1].timestamp() * 1000))
        if upd_logs is not None:
            df = pd.concat([df, upd_logs])
            with fig.batch_update():
                fig.data[0].x = df["timestamp"]  # Price line
                fig.data[0].y = df["price"]

                # Update BUY markers
                fig.data[1].x = df[df["order"] == "BUY"]["timestamp"]
                fig.data[1].y = df[df["order"] == "BUY"]["price"]

                # Update SELL markers
                fig.data[2].x = df[df["order"] == "SELL"]["timestamp"]
                fig.data[2].y = df[df["order"] == "SELL"]["price"]
            chart.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})


        time.sleep(5)
    # for i in range(len(df)):  # Go through the DataFrame row by row
    #     row = df.iloc[i]
    #
    #     # Append data
    #     with fig.batch_update():
    #         fig.data[0].x = df["timestamp"][:i+1]  # Price line
    #         fig.data[0].y = df["price"][:i+1]
    #
    #         # Update BUY markers
    #         fig.data[1].x = df[:i+1][df["order"] == "BUY"]["timestamp"]
    #         fig.data[1].y = df[:i+1][df["order"] == "BUY"]["price"]
    #
    #         # Update SELL markers
    #         fig.data[2].x = df[:i+1][df["order"] == "SELL"]["timestamp"]
    #         fig.data[2].y = df[:i+1][df["order"] == "SELL"]["price"]
    #
    #     # Update chart
    #     chart.plotly_chart(fig, use_container_width=True)
    #
    #     # Simulate real-time delay
    #     time.sleep(2)


# Static plotting function
def static_strategy_plot(df: pd.DataFrame):

    fig = go.Figure()
    # Plot price line
    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["price"], mode='lines', name='Price'))

    # Plot BUY markers
    buy_df = df[df["order"] == "BUY"]
    fig.add_trace(go.Scatter(
        x=buy_df["timestamp"],
        y=buy_df["price"],
        mode='markers',
        marker=dict(color='green', size=10, symbol=100),
        name='BUY'
    ))

    # Plot SELL markers
    sell_df = df[df["order"] == "SELL"]
    fig.add_trace(go.Scatter(
        x=sell_df["timestamp"],
        y=sell_df["price"],
        mode='markers',
        marker=dict(color='red', size=10, symbol=100),
        name='SELL'
    ))

    # Display chart
    st.plotly_chart(fig, use_container_width=True)