from streamlit import write, form, selectbox, radio, form_submit_button, sidebar, columns, number_input, toggle, multiselect, info, html, select_slider, divider, caption, container, spinner, pills
from frontend.src.library.analytics_helper.plots import price_history_plot, price_history_correlation_heatmap, show_line_plot_with_analytics, show_analytics
from frontend.src.library.analytics_helper.client import fetch_available_assets, fetch_price_history, fetch_symbol_analytics
from frontend.src.library.analytics_helper.funcs import invert_dict
from pandas import DataFrame, to_datetime

def get_price_analytics_form():
    html("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Crypto Analysis</h5>""")
    with container(border=True):
        with spinner("Fetching available assets..."):
            all_assets = fetch_available_assets("binance", quote_asset="all")
            all_assets = invert_dict(all_assets) # now the base assets are keys and the quote assets the values

        base_asset = selectbox(label='Choose Base Asset', options=all_assets.keys(),
                               help="This is the asset you will analyse")

        with form(key='forecasting_form', border=False, clear_on_submit=False):

            cols = columns(3)
            with cols[0]:
                default_index = all_assets[base_asset].index("USDT") if "USDT" in all_assets[base_asset] else 0
                quote_asset = selectbox(label='Choose Quote Asset', options=all_assets[base_asset], index=default_index)
            with cols[1]:
                time_limit = number_input('Choose Sample Time Limit', value=1000, min_value=100, max_value=1000000)
            with cols[2]:
                selectbox(label='Choose Exchange', options=["Binance"], disabled=True, help="The default exchange is Binance, since it contains the most markets available. Does not require an API key.")

            time_int = select_slider('Choose Time Interval ⏱️',
                                        ['1 minute', '5 minutes', '15 minutes', '30 minutes', '1 hour',
                                         '4 hours', '12 hours', '1 day', '2 days', '3 days', '5 days',
                                         '1 week', '1 month'], value='30 minutes')

            pills("Metrics", options=["RSI", "EMA", "Bollinger Bands"],disabled=True)
            plot_type = radio('Plot type', options=['Line Plot', 'Candle Plot'], index=0, horizontal=True)
            caption("For Price Forecasting summon the Oracle 🔮 in the forecasting tab.")
            divider()  # html("""<hr style="height:1px;width:12em;text-align:left; color:gray; background-color:gray; padding-top:0;">""")
            sumbit_button = form_submit_button('Call the Analyst 🕵️‍♂️')
            if sumbit_button:
                exchange_api = "binance"  # exchange_api.replace(' ', '_').lower()
                time_int_dict = {'1 minute': '1m', '5 minutes': '5m', '15 minutes': '15m', '30 minutes': '30m',
                                 '1 hour': '1h', '4 hours': '4h',
                                 '12 hours': '12h', '1 day': '1d', '2 days': '2d', '3 days': '3d', '5 days': '5d',
                                 '1 week': '1w', '1 month': '1M'}

                if plot_type == 'Candle Plot':
                    price_history_plot("binance", f"{base_asset}{quote_asset}", time_int_dict[time_int], time_limit, "Candle Plot")
                else:

                    # Fetch data
                    df, score = fetch_symbol_analytics("binance", f"{base_asset}{quote_asset}", time_int_dict[time_int], time_limit)
                    # SHOW ANALYTICS
                    show_analytics(quote_asset, base_asset, df, score)
                    # SHOW LINE PLOT
                    show_line_plot_with_analytics(f"{base_asset}{quote_asset}", df)

                sidebar.download_button(
                    "Download to CSV",
                    df.to_csv(index=False).encode('utf-8'),
                    f"{base_asset}{quote_asset}_{time_int}_price_history.csv",
                    "text/csv",
                    key='download-csv',
                    use_container_width=True,
                    icon=":material/download:"
                )
    return



def get_correlation_heatmap_form():
    html("<h5 style='text-align: left;margin-top:0; padding-top:0;'>Correlation Heatmap</h5>")
    write('Generate a Correlation Heatmap for the selected Crypto assets')
    caption("This function currently uses the Binance API to fetch the price")
    with form('Correlation Heatmap'):
        with spinner("Fetching available assets..."):
            base_assets = fetch_available_assets("binance", quote_asset="USDT")
        coins = multiselect(label='Choose Assets to Correlate', options=base_assets['USDT'], max_selections=40)
        cols1 = columns(2)
        with cols1[0]:
            time_int_c = selectbox(
                'Choose Date Interval',
                ('1m', '5m', '15m', '30m', '1h', '4h', '12h', '1d', '3d', '1w', '1M'), index=2)
        with cols1[1]:
            time_limit_c = number_input('Choose Sample Limit', value=500, min_value=2, max_value=10000)
        radio('Type of Correlation Formula',
                 options=['pearson', 'spearman', 'Distance', 'MIC', 'Regression Coefficients'], index=0,
                 horizontal=True, disabled=True, help='Feature coming soon')
        use_diff = toggle('Use Delta',
                             help='Calculate the Correlation based on the Diff (change in price) of each Coin and not its actual price')
        info("The Quote asset for each Coin is **USDT** by default.")
        corr_submit_button = form_submit_button('Get Correlation Heatmap', icon=":material/help:")
        if corr_submit_button:
            price_history_correlation_heatmap(coins, time_int_c, time_limit_c, use_diff)
    return
