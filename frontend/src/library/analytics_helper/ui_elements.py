from streamlit import write, form, selectbox, radio, form_submit_button, sidebar, columns, number_input, toggle, multiselect, session_state, html, select_slider, divider, caption
from frontend.src.library.analytics_helper.plots import price_history_plot, price_history_correlation_heatmap, show_line_plot_with_analytics, show_analytics
from frontend.src.library.analytics_helper.client import fetch_available_coins


def get_price_analytics_form():
    html("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Crypto Analysis</h5>""")
    with form(key='forecasting_form', border=True, clear_on_submit=False):
        cols = columns(3)
        with cols[0]:
            coin = selectbox(label='Choose Crypto Asset', options=fetch_available_coins())
        with cols[1]:
            if len(session_state["available_exchange_apis"]) == 0:
                exchange_api = "binance"
                selectbox(label='Choose Exchange', options=[], disabled=True)
            else:
                exchange_api = selectbox(label='Choose Exchange', options=session_state["available_exchange_apis"])
        with cols[2]:
            time_limit = number_input('Choose Sample Time Limit', value=1000, min_value=100, max_value=1000000)

        time_int = select_slider('Choose Time Horizon ⏱️',
                                    ['1 minute', '5 minutes', '15 minutes', '30 minutes', '1 hour',
                                     '4 hours', '12 hours', '1 day', '2 days', '3 days', '5 days',
                                     '1 week', '1 month'], value='30 minutes')

        advanced_analytics = toggle("Advanced Analytics", value=True, help="Advanced statistics include RSI, Bollinger Bands and more.")
        plot_type = radio('Plot type', options=['Line Plot', 'Candle Plot'], index=0, horizontal=True)
        caption("For Price Forecasting summon the Oracle 🔮 in the forecasting tab.")
        divider()  # html("""<hr style="height:1px;width:12em;text-align:left; color:gray; background-color:gray; padding-top:0;">""")
        sumbit_button = form_submit_button('Call the Analyst 🕵️‍♂️')
        if sumbit_button:
            exchange_api = exchange_api.replace(' ', '_').lower()
            time_int_dict = {'1 minute': '1m', '5 minutes': '5m', '15 minutes': '15m', '30 minutes': '30m',
                             '1 hour': '1h', '4 hours': '4h',
                             '12 hours': '12h', '1 day': '1d', '2 days': '2d', '3 days': '3d', '5 days': '5d',
                             '1 week': '1w', '1 month': '1M'}
            if advanced_analytics:
                price_hist_df = price_history_plot(exchange_api, coin, time_int_dict[time_int], time_limit, 'Candle Plot', False,
                                                   True)
                # SHOW ANALYTICS
                show_analytics(coin, price_hist_df)
                # SHOW LINE PLOT
                show_line_plot_with_analytics(coin, price_hist_df)
            else:
                price_hist_df = price_history_plot(exchange_api, coin, time_int_dict[time_int], time_limit, plot_type, True, True)

            sidebar.download_button(
                "Download to CSV",
                price_hist_df.to_csv(index=False).encode('utf-8'),
                coin+"_"+time_int+"_price_history.csv",
                "text/csv",
                key='download-csv',
                use_container_width=True,
                icon=":material/download:"
            )
    return


def get_price_history_form():
    html("<h5 style='text-align: left;margin-top:0; padding-top:0;'>Crypto Price History</h5>")
    write("Choose a coin and a time interval and visualize in a line-plot 📈 the price over time.")
    with form('Get Price'):
        cols = columns(3)
        with cols[0]:
            coin = selectbox(label='Choose Coin', options=fetch_available_coins())  # get the keys from the coin dict
            exchange_api = selectbox(label='Choose Exchange', options=session_state["available_exchange_apis"])
        with cols[1]:
            time_int = selectbox(
                'Choose Date Interval',
                ('1m', '5m', '15m', '30m', '1h', '4h', '12h', '1d', '3d', '1w', '1M'))
        with cols[2]:
            time_limit = number_input('Choose Sample Limit', value=500, min_value=2, max_value=1000000)

        plot_type = radio('Plot type', options=['Line Plot', 'Candle Plot'], index=0, horizontal=True)

        sumbit_button = form_submit_button('Submit')
        if sumbit_button:
            exchange_api = exchange_api.replace(' ', '_').lower()
            price_hist_df = price_history_plot(exchange_api, coin, time_int, time_limit, plot_type, True, True)
            sidebar.download_button(
                "Download to CSV",
                price_hist_df.to_csv(index=False).encode('utf-8'),
                coin+"_"+time_int+"_price_history.csv",
                "text/csv",
                key='download-csv'
            )
    return


def get_correlation_heatmap_form():
    html("<h5 style='text-align: left;margin-top:0; padding-top:0;'>Correlation Heatmap</h5>")
    write('Generate a Correlation Heatmap for the selected Crypto Coins')
    caption("This function currently uses the Binance API to fetch the price")
    with form('Correlation Heatmap'):
        coins = multiselect(label='Choose Coins to Correlate', options=fetch_available_coins(), max_selections=40)
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

        corr_sumbit_button = form_submit_button('Submit')
        if corr_sumbit_button:
            price_history_correlation_heatmap(coins, time_int_c, time_limit_c, use_diff)
    return
