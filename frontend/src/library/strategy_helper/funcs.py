from extra_streamlit_components import stepper_bar
from streamlit import write, container, expander, info, html, caption, link_button


def get_strategy_instructions(exp=False):

    # with popover('📖 Trading Instructions', use_container_width=True, help='fdfd'):
    with expander('📖 Trading Instructions', expanded=exp):
        str_val = stepper_bar(steps=["Asset Options", "Trading Options", "Algorithm & Parameters", "Submission"], lock_sequence=False)

        if str_val == 0:
            with container(border=False):
                html("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Asset Options</h5>""")
                write("1. Choose a ***Base Asset (from)***: This is the asset which you have to have in the account and will be use to buy the Target Asset")
                caption("Currently only USDT is available as an Asset to use for Trading.")
                write("2. Choose a ***Quote Asset (to)***: This is the asset which you will buy, using the Base Asset.")
                write("3. Choose a ***Buying Amount***: This indicates how much of ***Base Asset*** (i.e. USDT) you will spend.")

                write("E.g. To spend 20 USDT to buy BTC, you will choose -Base Asset: USDT, -Buying Amount: 20 and Quote Asset: BTC.")
        if str_val == 1:
            with container(border=False):
                html("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Trading & Convert</h5>""")
                write("The Binance **Convert** API enables trading with **0 fees**. If the backend server doesn't find a valid Convert API, the standard buy/sell order will be used. In that case make sure to have BNB in your account in order to minimize the fees.")
                write("Check if you are eligible for the Convert functionality in the sidebar 👈.")
                info("💡 In case of **Binance**, make sure to have **BNB** in your account in order to minimize the fees.")

        if str_val == 2:
            with container(border=False):
                html("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Algorithm & Parameters</h5>""")
                write('Choose an algorithm from the given list in order to deploy a Strategy. The algorithms are:')
                write('1. Greedy')
                write('2. Forecasting Model')
                write('3. Arbitrage Trading')
                write('4. DCA')
                write('5. Sibyl Algorithm')

                write('Each Algorithm contains a list of parameters that can be tuned, in order to define risk, stop-loss etc.')
                write("Currently only **Greedy** Algorithms is available.")
        if str_val == 3:
            with container(border=False):
                html("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Submission</h5>""")
                write('After the Strategy is submitted, it will be parsed and sent to the Exchange API. If it is successful you can track its progress in the Trading Report module.')
                link_button("Trading Report", "http://localhost:8501/trading_report ", type="primary", icon=":material/youtube_searched_for:")