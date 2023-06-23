from streamlit import sidebar, spinner, dataframe, plotly_chart
from library.history_helper.client import update_trading_history, fetch_trading_history
from pandas import DataFrame, to_datetime
from plotly.express import bar
from plotly.graph_objects import Figure, Scatter
from library.analytics_helper.plots import price_history_plot


def sidebar_update_history():
    if sidebar.button('Update History'):
        with spinner('Fetching latest Strategy History Status'):
            res = update_trading_history()
            if res.status_code == 200:
                if "success" in res.json():
                    sidebar.success(res.json())
                else:
                    sidebar.error(res.json())
            else:
                sidebar.error(res.json())


def trading_history_table(strat_status='all'):
    trade_strategies = fetch_trading_history(strat_status)
    df_strategy = DataFrame(columns=['Exchange', 'DateTime', 'buy_orderId', 'from_asset', 'to_asset', 'from_amount',
                                        'quantity_bought', 'from_price', 'DateTime [Sell]', 'sell_orderId',
                                        'price_to_sell',
                                        'Order Type', 'Strategy', 'Status'],
                               data=trade_strategies)
    # df_strategy['DateTime'] = pd.to_datetime(df_strategy['DateTime'], unit='s')
    # dataframe(df_strategy)
    return df_strategy


def get_status_barplot(status_series=None):
    colors = {
        'active': '#50C878',
        'partially_completed': '#ADD8E6',
        'completed': '#0073CF',
        'cancelled': '#E34234'
    }
    status_counts = status_series.value_counts().reindex(
        ['active', 'partially_completed', 'completed', 'cancelled'], fill_value=0)
    fig = bar(status_counts, x=status_counts.index, y=status_counts.values, color=status_counts.index,
              color_discrete_map=colors)
    fig.update_layout(xaxis={'type': 'category'}, yaxis_title='Number of Occurrences')
    plotly_chart(fig, config=dict(displayModeBar=False))


def get_trading_history_line_plot(trade_df=None, target_coin='Bitcoin [BTC]'):
    price_hist_df = price_history_plot(target_coin, '1h', 500,  'Line Plot', False)
    print(price_hist_df)
    # trade_df = DataFrame({
    #     'buy_datetime': ['2023-06-02', '2023-06-04', '2023-06-01', '2023-06-03'],
    #     'sell_datetime': ['2023-06-03', '2023-06-05', '2023-06-02', '2023-06-04'],
    #     'status': ['profit', 'loss', 'profit', 'loss']
    # })

    # Convert datetime columns to pandas DateTime objects
    price_hist_df['DateTime'] = to_datetime(price_hist_df['DateTime'])
    trade_df['DateTime'] = to_datetime(trade_df['DateTime']).dt.round('H')
    trade_df['DateTime [Sell]'] = to_datetime(trade_df['DateTime [Sell]']).dt.round('H')

    # Create a dictionary to map status values to numerical symbols
    status_symbols = {'Greedy': 106, 'Oracle': 206}
    # Create the figure
    fig = Figure()
    # Add the line plot
    fig.add_trace(Scatter(
        x=price_hist_df['DateTime'],
        y=price_hist_df['Price'],
        mode='lines',
        name=target_coin+' Price'
    ))

    # Iterate over each buy/sell pair and add a separate scatter trace
    for i, pair in trade_df.iterrows():
        buy_dt = pair['DateTime']
        sell_dt = pair['DateTime [Sell]']
        status = pair['Strategy']

        # Add scatter trace for the buy point
        fig.add_trace(Scatter(
            x=[buy_dt],
            y=[price_hist_df[price_hist_df['DateTime'] == buy_dt]['Price'].values[0]],
            mode='markers',
            marker=dict(color='green', size=16, symbol=status_symbols[status]),
            name=f'Buy {i + 1}',
            text=f'Buy Date: {buy_dt}<br>Buy Price: {price_hist_df[price_hist_df["DateTime"] == buy_dt]["Price"].values[0]}',
            hoverinfo='text'
        ))

        # Add scatter trace for the sell point
        fig.add_trace(Scatter(
            x=[sell_dt],
            y=[price_hist_df[price_hist_df['DateTime'] == sell_dt]['Price'].values[0]],
            mode='markers',
            marker=dict(color='red', size=16, symbol=status_symbols[status]),
            name=f'Sell {i + 1}',
            text=f'Sell Date: {sell_dt}<br>Sell Price: {price_hist_df[price_hist_df["DateTime"] == sell_dt]["Price"].values[0]}',
            hoverinfo='text'
        ))

    # Set plot layout
    fig.update_layout(
        title= target_coin + ' Price with Buy/Sell Points',
        xaxis_title='Date',
        yaxis_title='Price'
    )

    return fig
