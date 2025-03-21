import streamlit as st
import time
import plotly.graph_objs as go
import numpy as np


def get_real_time_data():
    return np.random.random(), time.time()


@st.fragment()
def real_time_strategy_plot():

    # Function to simulate real-time data (e.g., fetching from an API)

    # Create a placeholder for the Plotly chart
    st.title('Real-time Data Plot with Plotly')
    chart = st.empty()

    # Initialize data containers
    data = []
    timestamps = []

    # Create the initial plotly figure
    fig = go.Figure()

    # Add an initial trace to the figure (empty trace to start with)
    fig.add_trace(go.Scatter(x=[], y=[], mode='lines+markers', name='Real-time Data'))

    # Plot the initial empty figure
    chart.plotly_chart(fig, use_container_width=True)

    # Real-time update loop
    for _ in range(100):  # Loop 100 times for simulation
        # Get new data from your API or data source
        value, timestamp = get_real_time_data()

        # Append new data
        data.append(value)
        timestamps.append(timestamp)

        # Using batch_update to update the figure efficiently
        with fig.batch_update():
            fig.data[0].x = timestamps
            fig.data[0].y = data

        # Update the plot in Streamlit
        chart.plotly_chart(fig, use_container_width=True)

        # Sleep for the next update (simulating real-time data fetch)
        time.sleep(1.0)  # Sleep for 300ms between updates
