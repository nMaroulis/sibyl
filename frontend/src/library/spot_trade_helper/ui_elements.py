from extra_streamlit_components import stepper_bar
from streamlit import write, container, expander, info, html, caption, link_button


def get_spot_trade_instructions(exp=False):

    with expander('📖 Trading Instructions', expanded=exp):
        str_val = stepper_bar(steps=["Asset Options", "Trading Options", "Exchange Parameters", "Submission"], lock_sequence=False)
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
                write("You can find ***Open Positions*** and ****Trading History*** in the **Trading Report module**.")
                link_button("Trading Report", "http://localhost:8501/trading_report ", type="primary", icon=":material/youtube_searched_for:")