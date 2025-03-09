from extra_streamlit_components import stepper_bar
from streamlit import write, container, expander, info, html, caption, link_button, tabs, error, info


def get_spot_trade_instructions(exp=False):

    with expander('📖 Trading Instructions', expanded=exp):
        str_val = stepper_bar(steps=["Asset Options", "Trading Options", "Exchange Parameters", "Submission"], lock_sequence=False)
        if str_val == 0:
            with container(border=False):
                html("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Asset Options</h5>""")
                tab0, tab1 = tabs(["Standard Order", "Quote Market Order"])
                with tab0:
                    write("1. Choose a ***Quote Asset***: This is the asset which you have to have in the account and will be use to **Buy** the **Base Asset**")
                    caption("Currently only USDT is available as an Asset to use for Trading.")
                    write("2. Choose a ***Base Asset***: This is the asset which you will buy, using the Quote Asset.")
                    write("3. Choose a ***Quantity***: This indicates how much of ***Base Asset*** (e.g. BTC) you will buy.")
                    write("**Example**: To buy 1 ETH with USDT you have on your account, you will choose: -Quote Asset: USDT, - Base Asset: ETH, quantity: 1.")
                with tab1:
                    write("This option is similar to the standard order, the only difference is you specify the amount of the Quote Asset you want to spend.")
                    write("**Example**: You want to buy 10 USDT worth of ETH. You will choose: -Quote Asset: USDT, - Base Asset: ETH, quote_quantity: 10. This way you define how much you want to spend and not how much you want to buy.")
                    info("**Note**: This option is only available in Market orders.", icon=":material/info:")
                    error("This option is not yet available.", icon=":material/warning:")
        if str_val == 1:
            with container(border=False):
                html("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Trading Options</h5>""")
        if str_val == 2:
            with container(border=False):
                html("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Exchange Parameters</h5>""")
                write("The Binance **Convert** API enables trading with **0 fees**. If the backend server doesn't find a valid Convert API, the standard order will be used.")
                write("If you are eligible to use the Convert functionality, the corresponding option will be shown below.")
                info("💡 For **Binance**, make sure to have **BNB** in your account in order to minimize the fees.")
        if str_val == 3:
            with container(border=False):
                html("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Submission</h5>""")
                write('First, a **test order** will be created to test if the order is possible based on the trade parameters. If it is not a message with the error from the Exchange API will be shown, otherwise the Trade will be placed.')
                write("You can find ***Open Positions*** and ***Trading History*** in the **Trading Report module**.")
                link_button("Trading Report", "http://localhost:8501/trading_report ", type="primary", icon=":material/youtube_searched_for:")