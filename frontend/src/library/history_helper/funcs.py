from streamlit import sidebar, spinner, dataframe, plotly_chart, warning, error
from frontend.src.library.history_helper.client import update_trading_history, fetch_trading_history
from pandas import DataFrame, to_datetime, isnull
from plotly.graph_objects import Figure, Scatter, Pie
from frontend.src.library.analytics_helper.plots import price_history_plot
from frontend.src.library.crypto_dictionary_assistant import get_crypto_coin_dict_inv
from plotly.subplots import make_subplots


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
    return df_strategy.sort_values(by='DateTime', ascending=False)


def get_status_barplot(status_series=None):
    colors = {
        'active': '#50C878',
        'partially_completed': '#ADD8E6',
        'completed': '#0073CF',
        'cancelled': '#E34234'
    }
    # status_counts = status_series.value_counts().reindex(
    #     ['active', 'partially_completed', 'completed', 'cancelled'], fill_value=0)
    # fig = bar(status_counts, x=status_counts.index, y=status_counts.values, color=status_counts.index,
    #           color_discrete_map=colors)
    # fig.update_layout(xaxis={'type': 'category'}, yaxis_title='Number of Occurrences')
    status_counts = status_series.value_counts()
    fig = Figure(data=[Pie(labels=status_counts.index, values=status_counts.values, hole=0.5, textinfo='value+percent')])
    fig.update_traces(marker=dict(colors=[colors[status] for status in status_counts.index]))
    plotly_chart(fig, config=dict(displayModeBar=False))


def get_trading_history_line_plot(trade_df=None, target_coin='Bitcoin [BTC]'):

    if trade_df.shape[0] > 5:
        warning("💡 A maximum of **5 Trades** can be plotted concurrently!")  # trade_df = trade_df[0:4]
        return None
    if len(list(trade_df['to_asset'].unique())) > 2:
        warning("⚠️ A maximum of **2** different traded Coins [to_asset] can be plotted concurrently!")  # trade_df = trade_df[0:4]
        return None

    trade_df['DateTime'] = to_datetime(trade_df['DateTime']).dt.round('30min')
    trade_df['DateTime [Sell]'] = to_datetime(trade_df['DateTime [Sell]']).dt.round('30min')
    coins_list = list(trade_df['to_asset'].unique())
    more_that_one_coins_flag = False
    if len(coins_list) > 1:
        coins_list = coins_list[0:2]
        more_that_one_coins_flag = True

    # Get Historic Prices
    price_hist_df = price_history_plot(get_crypto_coin_dict_inv().get(coins_list[0]), '30m', 500,  'Line Plot', False)
    col_name = coins_list[0] + ' Price'
    price_hist_df[col_name] = price_hist_df['Price']
    if more_that_one_coins_flag:
        price_hist_df_tmp = price_history_plot(get_crypto_coin_dict_inv().get(coins_list[1]), '30m', 500, 'Line Plot', False)
        col_name1 = coins_list[1] + ' Price'
        price_hist_df[col_name1] = price_hist_df_tmp['Price']

    # Convert datetime columns to pandas DateTime objects
    price_hist_df['DateTime'] = to_datetime(price_hist_df['DateTime']).dt.round('30min')

    # Support a maximum of 4 concurrent plots
    # Different marker shape for each buy/sell order
    status_symbols = [100, 106, 102, 101, 117] # open circle, triangle-down, diamond, square, star
    # status_symbols = {'Greedy': 106, 'Oracle': 206} # Create a dictionary to map status values to numerical symbols

    # Create the figure
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    # Add the line plot
    fig.add_trace(Scatter(
        x=price_hist_df['DateTime'],
        y=price_hist_df[col_name],
        mode='lines',
        name=coins_list[0]+' Price'
    ))

    if more_that_one_coins_flag:
        fig.add_trace(Scatter(
            x=price_hist_df['DateTime'],
            y=price_hist_df[col_name1],
            mode='lines',
            name=coins_list[1]+' Price',
        ), secondary_y=True,)

    # Iterate over each buy/sell pair and add a separate scatter trace
    for i, pair in trade_df.iterrows():
        buy_dt = pair['DateTime']
        sell_dt = pair['DateTime [Sell]']
        status = pair['Strategy']
        price_col = pair['to_asset'] + ' Price'

        if pair['to_asset'] == coins_list[0]:
            secondary_plot = False
        else:
            secondary_plot = True

        if len(price_hist_df[price_hist_df['DateTime'] == buy_dt][price_col].values) <1:
            error('Plot for old dates is not supported yet!')
            return None
        # Add scatter trace for the buy point
        fig.add_trace(Scatter(
            x=[buy_dt],
            y=[price_hist_df[price_hist_df['DateTime'] == buy_dt][price_col].values[0]],
            mode='markers',
            marker=dict(color='green', size=16, symbol=status_symbols[i]),
            name=f'Buy {i+1}: {status}',
            text=f'Buy Date: {buy_dt}<br>Buy Price: {price_hist_df[price_hist_df["DateTime"] == buy_dt][price_col].values[0]}',
            hoverinfo='text'
        ), secondary_y=secondary_plot)

        if not isnull(sell_dt):  # 'NaT'
            # Add scatter trace for the sell point
            fig.add_trace(Scatter(
                x=[sell_dt],
                y=[price_hist_df[price_hist_df['DateTime'] == sell_dt][price_col].values[0]], # add [] around y, if it doesnt work
                mode='markers',
                marker=dict(color='red', size=16, symbol=status_symbols[i]),
                name=f'Sell {i+1}: {status}',
                text=f'Sell Date: {sell_dt}<br>Sell Price: {price_hist_df[price_hist_df["DateTime"] == sell_dt][price_col].values[0]}',
                hoverinfo='text'
            ), secondary_y=secondary_plot)

    # Set plot layout
    fig.update_layout(
        title= str(coins_list) + ' Price with Buy/Sell Points',
        xaxis_title='Date',
        yaxis_title='Price'
    )

    return fig
