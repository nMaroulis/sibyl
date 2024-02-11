from pandas import DataFrame, to_datetime
from plotly.graph_objects import Figure, Scatter, Candlestick
from streamlit import plotly_chart, warning
from frontend.src.library.analytics_helper.client import fetch_price_history
from plotly.express import imshow


def price_history_plot(coin='BTC', time_int='1d', time_limit=500, plot_type='Line Plot', show_plot=True, full_name=True):
    df = DataFrame()
    fig = None
    if plot_type == 'Line Plot':
        data = fetch_price_history(coin, time_int, time_limit, 'line', full_name)
        df['DateTime'] = [entry.get('Open Time') for entry in data]
        df['DateTime'] = to_datetime(df['DateTime'], unit='ms')
        df['Price'] = [entry.get('Open Price') for entry in data]

        if show_plot:
            fig = Figure(data=Scatter(x=df['DateTime'], y=df['Price']))
            fig.update_layout(title=f"Price History of ada", xaxis_title="DateTime",  yaxis_title="Price (USDT)")
    else:  # candle plot

        data = fetch_price_history(coin, time_int, time_limit, 'candle', full_name)
        df['DateTime'] = [entry.get('Open Time') for entry in data]
        df['DateTime'] = to_datetime(df['DateTime'], unit='ms')
        df['Open Price'] = [entry.get('Open Price') for entry in data]
        df['Highs'] = [entry.get('Highs') for entry in data]
        df['Lows'] = [entry.get('Lows') for entry in data]
        df['Closing Price'] = [entry.get('Closing Price') for entry in data]

        if show_plot:
            fig = Figure(data=Candlestick(
                x=df['DateTime'],
                open=df['Open Price'],
                high=df['Highs'],
                low=df['Lows'],
                close=df['Closing Price']
            ))
            fig.update_layout(title=coin + ' Price History')

    if show_plot and fig is not None:
        plotly_chart(fig, use_container_width=True)
    return df


def price_history_correlation_heatmap(coins, time_int_c='1d', time_limit_c=500, use_diff=False):
    df = DataFrame()
    invalid_coins = []
    for coin in coins:
        price_hist_df = price_history_plot(coin, time_int_c, time_limit_c, 'Line Plot', False, True)
        if price_hist_df.shape[0] < 2:
            invalid_coins.append(coin)
        else:
            df[coin] = price_hist_df['Price'].astype(float)
    if use_diff:
        df = df.diff()

    if len(invalid_coins) > 0:
        warning('Price for **' + str(invalid_coins) + '** could not be fetched from the Server.')

    df_corr = df.corr(method='pearson')
    fig = imshow(df_corr, text_auto=True, aspect="auto", color_continuous_scale='RdBu_r')
    plotly_chart(fig, use_container_width=True)
