from streamlit import markdown, write, form, selectbox, radio, form_submit_button, sidebar, columns, number_input, toggle, multiselect
from frontend.src.library.analytics_helper.plots import price_history_plot, price_history_correlation_heatmap
from frontend.src.library.analytics_helper.client import fetch_available_coins


def get_price_history_form():
    markdown("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Crypto Price History</h5>""",
             unsafe_allow_html=True)
    write("Choose a coin and a time interval and visualize in a line-plot 📈 the price over time.")
    with form('Get Price'):
        cols = columns(3)
        with cols[0]:
            coin = selectbox(label='Choose Coin', options=fetch_available_coins())  # get the keys from the coin dict
            exchange_api = selectbox(label='Choose Exchange', options=['binance_testnet'])
        with cols[1]:
            time_int = selectbox(
                'Choose Date Interval',
                ('1m', '5m', '15m', '30m', '1h', '4h', '12h', '1d', '3d', '1w', '1M'))
        with cols[2]:
            time_limit = number_input('Choose Sample Limit', value=500, min_value=2, max_value=1000000)

        plot_type = radio('Plot type', options=['Line Plot', 'Candle Plot'], index=0, horizontal=True)

        sumbit_button = form_submit_button('Submit')
        if sumbit_button:
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
    markdown("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Correlation Heatmap</h5>""",
                unsafe_allow_html=True)
    write('Generate a Correlation Heatmap for the selected Crypto Coins')
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
