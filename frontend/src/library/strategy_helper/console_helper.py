import streamlit as st
import time
import plotly.graph_objs as go
import numpy as np
import pandas as pd

# Function to generate a random initial DataFrame
def generate_random_df(size=50):
    timestamps = np.arange(size)
    prices = np.cumsum(np.random.randn(size)) + 100  # Simulated price movement
    orders = np.random.choice(["BUY", "SELL", "HOLD"], size=size)
    return pd.DataFrame({"timestamp": timestamps, "price": prices, "order": orders})

# Function to simulate fetching new data
def get_real_time_data():
    new_timestamp = np.random.randint(100, 200)
    new_price = np.random.uniform(90, 110)
    new_order = np.random.choice(["BUY", "SELL", "HOLD"])
    return new_timestamp, new_price, new_order


@st.fragment()
def real_time_strategy_plot(df: pd.DataFrame):
    st.title('Real-time Trading Strategy Plot')

    # Create a placeholder for the Plotly chart
    chart = st.empty()

    # Initialize figure
    fig = go.Figure()

    # Add initial traces
    fig.add_trace(go.Scatter(x=[], y=[], mode='lines', name='Price'))
    fig.add_trace(go.Scatter(x=[], y=[], mode='markers', marker=dict(color='green', size=10), name='BUY'))
    fig.add_trace(go.Scatter(x=[], y=[], mode='markers', marker=dict(color='red', size=10), name='SELL'))

    # Display the empty chart
    chart.plotly_chart(fig, use_container_width=True)

    # Real-time update loop
    for i in range(len(df)):  # Go through the DataFrame row by row
        row = df.iloc[i]

        # Append data
        with fig.batch_update():
            fig.data[0].x = df["timestamp"][:i+1]  # Price line
            fig.data[0].y = df["price"][:i+1]

            # Update BUY markers
            fig.data[1].x = df[df["order"] == "BUY"]["timestamp"][:i+1]
            fig.data[1].y = df[df["order"] == "BUY"]["price"][:i+1]

            # Update SELL markers
            fig.data[2].x = df[df["order"] == "SELL"]["timestamp"][:i+1]
            fig.data[2].y = df[df["order"] == "SELL"]["price"][:i+1]

        # Update chart
        chart.plotly_chart(fig, use_container_width=True)

        # Simulate real-time delay
        time.sleep(1)


# Static plotting function
def static_strategy_plot(df: pd.DataFrame):

    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
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