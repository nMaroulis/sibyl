from streamlit import spinner, dataframe, metric, write, plotly_chart
from plotly.graph_objects import Figure, Scatter
from frontend.src.library.forecasting_helper.funcs import calc_rsi, calc_ema, calc_bollinger_bands
import pandas as pd


def show_analytics(coin, df):
    with spinner('The Oracle is forecasting the future...'):
        dataframe(df)
        metric(f'{coin} Price in USDT', float(df['Closing Price'].iloc[-1]),
               round(float(df['Closing Price'].iloc[-1]) - float(df['Closing Price'].iloc[-2]), 6))
    return


def show_line_plot_with_analytics(coin, price_hist_df):
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
            x=pd.concat([price_hist_df['DateTime'], price_hist_df['DateTime'][::-1]]),
            y=pd.concat([price_hist_df['UpperBand'], price_hist_df['LowerBand'][::-1]]),
            fill='toself', fillcolor='rgba(255, 165, 0, 0.5)',
            line=dict(color='rgba(255, 165, 0, 0)'), name='Bollinger Bands Interval'))

        fig.add_trace(
            Scatter(x=price_hist_df['DateTime'], y=price_hist_df['RSI'], mode='lines', yaxis="y2", name='RSI', opacity=0.5,
                    line=dict(color='purple')))
        fig.update_layout(title=f'{coin} Price Analysis', xaxis_title='Date', yaxis_title='Price',
                          yaxis2=dict(title='RSI', overlaying='y', side='right'), showlegend=True)
        plotly_chart(fig, use_container_width=True)

    return
