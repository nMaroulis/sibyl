from pandas import DataFrame, to_datetime, concat
from plotly.graph_objects import Figure, Scatter, Candlestick
from streamlit import plotly_chart, warning, spinner, html, metric, write
from frontend.src.library.analytics_helper.client import fetch_price_history
from plotly.express import imshow
from frontend.src.library.forecasting_helper.funcs import calc_rsi, calc_ema, calc_bollinger_bands


def show_analytics(quote_asset: str, base_asset: str, df: DataFrame):
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
        metric(f'{base_asset} Price in {quote_asset}', float(df['Close Price'].iloc[-1]),
               round(float(df['Close Price'].iloc[-1]) - float(df['Close Price'].iloc[-2]), 6))
    return


def show_line_plot_with_analytics(pair_symbol: str, price_hist_df: DataFrame):
    write(
        "**Exponential Moving Average (EMA)**: A Moving Average that places more weight on recent price data, reacting faster to price changes compared to the simple moving average (SMA). It's calculated using an exponential decay formula, giving higher importance to recent data points.")
    write(
        "**Relative Strength Index (RSI)**: RSI is a momentum oscillator that measures the speed and magnitude of price movements. It compares recent gains to losses, typically over a 14-day period, to determine whether a security is overbought or oversold. RSI values range from 0 to 100, with readings above 70 indicating overbought conditions and readings below 30 indicating oversold conditions.")
    write(
        "**Bollinger Bands** consist of three lines on a price chart: the middle band, the exponential moving average (EMA) over a specified period (e.g., 20 days); the upper band, calculated by adding two standard deviations to the middle band; and the lower band, calculated by subtracting two standard deviations from the middle band. Bollinger Bands help traders gauge market volatility, identify potential overbought or oversold conditions, and anticipate price reversals.")
    with spinner('Generating Line Plot...'):

        price_hist_df['Moving Average'] = calc_ema("exponential", price_hist_df['Close Price'], 5)
        price_hist_df['RSI'] = calc_rsi(price_hist_df['Close Price'].astype(float), 14)
        price_hist_df['LowerBand'], price_hist_df['UpperBand'] = calc_bollinger_bands(price_hist_df['Moving Average'], price_hist_df['Close Price'], 3)

        fig = Figure()
        fig.add_trace(
            Scatter(x=price_hist_df['DateTime'], y=price_hist_df['Close Price'], mode='lines', name='Close Price'))
        fig.add_trace(Scatter(
            x=concat([price_hist_df['DateTime'], price_hist_df['DateTime'][::-1]]),
            y=concat([price_hist_df['UpperBand'], price_hist_df['LowerBand'][::-1]]),
            fill='toself', fillcolor='rgba(255, 165, 0, 0.5)',
            line=dict(color='rgba(255, 165, 0, 0)'), name='Bollinger Bands Interval'))

        fig.add_trace(
            Scatter(x=price_hist_df['DateTime'], y=price_hist_df['RSI'], mode='lines', yaxis="y2", name='RSI', opacity=0.5,
                    line=dict(color='purple')))
        fig.update_layout(title=f'{pair_symbol} Price Analysis', xaxis_title='Date', yaxis_title='Price',
                          yaxis2=dict(title='RSI', overlaying='y', side='right'), showlegend=True)
        plotly_chart(fig, use_container_width=True)

    return


def price_history_plot(exchange_api: str, pair_symbol: str, time_int: str, time_limit: int, plot_type : str = 'Line Plot') -> None:
    df = fetch_price_history(exchange_api, pair_symbol, time_int, time_limit)
    """
        "Open Time": entry[0],
        "Open Price": float(entry[1]),
        "High": float(entry[2]),
        "Low": float(entry[3]),
        "Close Price": float(entry[4]),
        "Close Time": float(entry[6]),
        "Volume": float(entry[5]),
        "Number of trades": float(entry[8]),
    """
    if df is not None:
        fig = None
        if plot_type == 'Line Plot':
            fig = Figure(data=Scatter(x=df['DateTime'], y=df['Price']))
            fig.update_layout(title=f"Price History of ada", xaxis_title="DateTime",  yaxis_title="Price (USDT)")
        else:  # candle plot
            fig = Figure(data=Candlestick(
                x=df['DateTime'],
                open=df['Open Price'],
                high=df['High'],
                low=df['Low'],
                close=df['Close Price']
            ))
            fig.update_layout(title=pair_symbol + ' Price History')

        if fig is not None:
            plotly_chart(fig, use_container_width=True)


def price_history_correlation_heatmap(coins, time_int_c='1d', time_limit_c=500, use_diff=False):
    corr_df = DataFrame()
    invalid_coins = []
    for coin in coins:
        pair_symbol = f"{coin}USDT"
        df = fetch_price_history("binance", pair_symbol, time_int_c, time_limit_c)

        if df is None or df.shape[0] < 2:
            invalid_coins.append(coin)
        else:
            corr_df[coin] = df['Close Price']

    if use_diff:
        corr_df = corr_df.diff()

    if len(invalid_coins) > 0:
        warning('Price for **' + str(invalid_coins) + '** could not be fetched from the Server.')

    corr_df = corr_df.corr(method='pearson')
    fig = imshow(corr_df, text_auto=True, aspect="auto", color_continuous_scale='RdBu_r')
    plotly_chart(fig, use_container_width=True)
