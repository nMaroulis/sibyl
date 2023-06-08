from pandas import DataFrame, to_datetime
from plotly.graph_objects import Figure, Scatter, Candlestick
from streamlit import plotly_chart
from library.analytics_helper.client import fetch_price_history


def price_history_plot(coin='BTC', time_int='1d', time_limit=500, plot_type='Line Plot'):
    df = DataFrame()
    if plot_type == 'Line Plot':
        data = fetch_price_history(coin, time_int, time_limit, 'line')
        df['DateTime'] = [entry.get('Open Time') for entry in data]
        df['DateTime'] = to_datetime(df['DateTime'], unit='ms')
        df['Price'] = [entry.get('Open Price') for entry in data]

        fig = Figure(data=Scatter(x=df['DateTime'], y=df['Price']))
        fig.update_layout(title=f"Price History of ada",
                          xaxis_title="DateTime",
                          yaxis_title="Price (USDT)")
    else:  # candle plot

        data = fetch_price_history(coin, time_int, time_limit, 'candle')
        df['DateTime'] = [entry.get('Open Time') for entry in data]
        df['DateTime'] = to_datetime(df['DateTime'], unit='ms')
        df['Open Price'] = [entry.get('Open Price') for entry in data]
        df['Highs'] = [entry.get('Highs') for entry in data]
        df['Lows'] = [entry.get('Lows') for entry in data]
        df['Closing Price'] = [entry.get('Closing Price') for entry in data]

        fig = Figure(data=Candlestick(
            x=df['DateTime'],
            open=df['Open Price'],
            high=df['Highs'],
            low=df['Lows'],
            close=df['Closing Price']
        ))
        # Set the chart title
        fig.update_layout(title=coin + ' Price History')

    plotly_chart(fig, use_container_width=True)
    return df
