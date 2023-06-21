from streamlit import sidebar, spinner, dataframe, plotly_chart
from library.history_helper.client import update_trading_history, fetch_trading_history
from pandas import DataFrame
from plotly.express import bar


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

    dataframe(df_strategy)
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
