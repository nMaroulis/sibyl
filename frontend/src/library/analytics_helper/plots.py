from pandas import DataFrame, to_datetime, concat
from plotly.graph_objects import Figure, Scatter, Candlestick
from streamlit import plotly_chart, warning, spinner, html, metric, write
from frontend.src.library.analytics_helper.client import fetch_price_history
from plotly.express import imshow
from frontend.src.library.forecasting_helper.funcs import calc_rsi, calc_ema, calc_bollinger_bands


def show_analytics(coin: str, df: DataFrame):
    with spinner('The Analyst is analyzing the data...'):
        # dataframe(df)
        html("""
            <style>
                .status_header {
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    padding: 4px 0;
                }
                .status_line {
                    flex-grow: 1;
                    height: 1px;
                    background-color: #ddd; /* Color of the line */
                }
                .status_title {
                    padding: 0 20px;
                    font-size: 21px;
                    color: #666;
                }
            </style>
            <div class="status_header">
                <div class="status_line"></div>
                <div class="status_title">Analyst Result</div>
                <div class="status_line"></div>
            </div>

        """)
        metric(f'{coin} Price in USDT', float(df['Closing Price'].iloc[-1]),
               round(float(df['Closing Price'].iloc[-1]) - float(df['Closing Price'].iloc[-2]), 6))
    return


def show_line_plot_with_analytics(coin: str, price_hist_df: DataFrame):
    write(
        "**Exponential Moving Average (EMA)**: A Moving Average that places more weight on recent price data, reacting faster to price changes compared to the simple moving average (SMA). It's calculated using an exponential decay formula, giving higher importance to recent data points.")
    write(
        "**Relative Strength Index (RSI)**: RSI is a momentum oscillator that measures the speed and magnitude of price movements. It compares recent gains to losses, typically over a 14-day period, to determine whether a security is overbought or oversold. RSI values range from 0 to 100, with readings above 70 indicating overbought conditions and readings below 30 indicating oversold conditions.")
    write(
        "**Bollinger Bands** consist of three lines on a price chart: the middle band, the exponential moving average (EMA) over a specified period (e.g., 20 days); the upper band, calculated by adding two standard deviations to the middle band; and the lower band, calculated by subtracting two standard deviations from the middle band. Bollinger Bands help traders gauge market volatility, identify potential overbought or oversold conditions, and anticipate price reversals.")
    with spinner('Generating Line Plot...'):

        price_hist_df['Moving Average'] = calc_ema("exponential", price_hist_df['Closing Price'], 5)
        price_hist_df['RSI'] = calc_rsi(price_hist_df['Closing Price'].astype(float), 14)
        price_hist_df['LowerBand'], price_hist_df['UpperBand'] = calc_bollinger_bands(price_hist_df['Moving Average'], price_hist_df['Closing Price'], 3)

        fig = Figure()
        fig.add_trace(
            Scatter(x=price_hist_df['DateTime'], y=price_hist_df['Closing Price'], mode='lines', name='Close Price'))
        fig.add_trace(Scatter(
            x=concat([price_hist_df['DateTime'], price_hist_df['DateTime'][::-1]]),
            y=concat([price_hist_df['UpperBand'], price_hist_df['LowerBand'][::-1]]),
            fill='toself', fillcolor='rgba(255, 165, 0, 0.5)',
            line=dict(color='rgba(255, 165, 0, 0)'), name='Bollinger Bands Interval'))

        fig.add_trace(
            Scatter(x=price_hist_df['DateTime'], y=price_hist_df['RSI'], mode='lines', yaxis="y2", name='RSI', opacity=0.5,
                    line=dict(color='purple')))
        fig.update_layout(title=f'{coin} Price Analysis', xaxis_title='Date', yaxis_title='Price',
                          yaxis2=dict(title='RSI', overlaying='y', side='right'), showlegend=True)
        plotly_chart(fig, use_container_width=True)

    return


def price_history_plot(exchange_api: str = 'binance_testnet', coin: str ='BTC', time_int: str = '1d', time_limit: int = 500, plot_type : str = 'Line Plot', show_plot=True, full_name=True):
    df = DataFrame()
    fig = None
    if plot_type == 'Line Plot':
        data = fetch_price_history(exchange_api, coin, time_int, time_limit, 'line', full_name)
        df['DateTime'] = [entry.get('Open Time') for entry in data]
        df['DateTime'] = to_datetime(df['DateTime'], unit='ms')
        df['Price'] = [entry.get('Open Price') for entry in data]

        if show_plot:
            fig = Figure(data=Scatter(x=df['DateTime'], y=df['Price']))
            fig.update_layout(title=f"Price History of ada", xaxis_title="DateTime",  yaxis_title="Price (USDT)")
    else:  # candle plot

        data = fetch_price_history(exchange_api, coin, time_int, time_limit, 'candle', full_name)
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
        price_hist_df = price_history_plot(coin, time_int_c, time_limit_c, 'Line Plot', False, True) # TODO - ADD DEFAULT PRICE HISTORY
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
