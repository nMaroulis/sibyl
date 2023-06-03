import requests
from pandas import DataFrame, to_datetime
from library.crypto_dictionary_assistant import get_crypto_coin_dict
from plotly.graph_objects import Figure, Scatter, Candlestick
from streamlit import plotly_chart


def price_history_plot(coin='BTC', time_int='1d', time_limit=500, plot_type='Line Plot'):

    if plot_type == 'Line Plot':
        url = f"http://127.0.0.1:8000/coin/price_history/" + get_crypto_coin_dict().get(
            coin) + "?interval=" + time_int + "&limit=" + str(time_limit) + "&plot_type=line"
        response = requests.get(url)
        data = response.json()

        df = DataFrame()

        df['DateTime'] = [entry.get('Open Time') for entry in data]
        df['DateTime'] = to_datetime(df['DateTime'], unit='ms')
        df['Price'] = [entry.get('Open Price') for entry in data]

        fig = Figure(data=Scatter(x=df['DateTime'], y=df['Price']))
        fig.update_layout(title=f"Price History of ada",
                          xaxis_title="DateTime",
                          yaxis_title="Price (USDT)")
    else: # candle plot
        url = f"http://127.0.0.1:8000/coin/price_history/" + get_crypto_coin_dict().get(
            coin) + "?interval=" + time_int + "&limit=" + str(time_limit) + "&plot_type=candle"
        response = requests.get(url)
        data = response.json()

        df = DataFrame()

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