import pandas as pd
import plotly.graph_objects as go
from streamlit import plotly_chart, metric
from frontend.src.library.forecasting_helper.client import fetch_oracle_forecast


def plot_forecast(coin: str, interval: str, forecast_samples: int):

    data = fetch_oracle_forecast(coin, interval, forecast_samples)
    df = pd.DataFrame(data)

    limit = df.shape[0] - forecast_samples
    metric("Price Diff.", round(float(df[-2:-1]['price'].values),2), delta=round(float(df[-2:-1]['price'].values)- float(df[limit-1:limit]['price'].values),2))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df[0:limit]['date'], y=df[0:limit]['price'],
                             mode='lines', name='Actual',
                             line=dict(color='blue', width=2)))

    fig.add_trace(go.Scatter(x=df[limit-1:-1]['date'], y=df[limit-1:-1]['price'],
                             mode='lines+markers', name='Prediction',
                             line=dict(color='rgba(255, 165, 0, 0.8)', width=2, shape='spline'),  # Smooth curve with transparency
                             marker=dict(size=6, color='orange', symbol='circle', line=dict(width=2, color='black')),
                             ))  # Gradient-like effect
    fig.update_layout(
        title='Price and Oracle Prediction',
        xaxis_title='Date',
        yaxis_title='Price',
        xaxis_tickangle=-45,
        hovermode='closest'  # Smooth hover interaction
    )
    plotly_chart(fig, use_container_width=True)