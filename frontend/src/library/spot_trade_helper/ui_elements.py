from extra_streamlit_components import stepper_bar
from streamlit import write, container, expander, info, html, caption, link_button, tabs, error, info, divider


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
                write("""**Order Type**""")
                write("""1. **Market Order** – Executes immediately at the current market price. Suitable for quick trades but may incur higher "taker" fees.""")
                write("""2. **Limit Order** – Allows you to set a specific price at which you want to buy or sell. This order is placed on the order book and may incur lower "maker" fees.""")
                write("""3. **Stop-Loss Order** – Triggers a market sell order when the asset price falls to a specified "stop price." Used to minimize losses.""")
                write("""4. **Stop-Loss Limit Order** – Similar to a stop-loss, but instead of triggering a market order, it places a limit order once the stop price is reached.""")
                write("""5. **Take-Profit Order** – A market order that executes when the asset reaches a specified price, allowing you to secure profits automatically.""")
                write("""6. **Take-Profit Limit Order** – Similar to a take-profit order but executes as a limit order at a defined price.""")
                write("""7. **Trailing Stop Order** – A stop order that moves dynamically with price changes, protecting profits while minimizing downside risk.""")
                write("""8. **OCO (One-Cancels-the-Other)** – Combines a limit order and a stop-loss order, where if one order is executed, the other is automatically canceled.""")
                divider()
                write("""**Order Side**""")
                write("""- **Buy** – Purchase the selected Base asset.""")
                write("""- **Sell** – Sell the selected Base asset.""")
                divider()
                write("""**Pricing Fields**""")
                write("""- **Limit Price** – The price at which you are willing to buy/sell for limit orders.""")
                write("""- **Stop Price** – The price at which stop-loss and stop-limit orders trigger.""")
                write("""- **Take-Profit Price** – The price at which take-profit orders execute.""")
                divider()
                write("""**Additional Options**""")
                write("""**Percentage Mode** – If enabled, Stop-Loss and Take-Profit levels will be calculated as percentages rather than absolute values.""")
                write("""**Post-Only Order** – Ensures your limit order adds liquidity to the market by preventing it from executing immediately.""")
                write("""Time in Force (TIF) Options""")
                write("""- **GTC (Good-Til-Canceled)** – The order stays open until fully executed or manually canceled.""")
                write("""- **IOC (Immediate-Or-Cancel)** – The order is executed immediately for available liquidity, and any remaining portion is canceled.
                    FOK""")
                write("""- **FOK (Fill-Or-Kill)** – The order must be fully executed immediately or canceled entirely.""")
                write("""**Iceberg Quantity**: If entering a large order, an iceberg order allows only a portion of the total order to be visible on the order book at a time, helping to prevent large trades from impacting the market significantly.""")
        if str_val == 2:
            with container(border=False):
                html("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Exchange Parameters</h5>""")
                write("**Token Swap Order**:")
                caption("Some Exchanges offer the **Token Swap** functionality, which directly swaps your Quote asset to the Base asset in market price with 0 fees.")
                write("1. The **Binance Convert** API enables trading with **0 fees**. If the backend server doesn't find a valid Convert API, the standard order will be used. If you are eligible to use the Convert functionality, the corresponding option will be shown below.")
                write("2. **Coinbase One** which provides zero trading fees among other benefits for a monthly fee of $29.99. This service allows users to buy, sell, and swap cryptocurrencies without incurring individual transaction fees, effectively enabling cost-effective crypto swaps.")
                write("3. Kraken has introduced a feature known as **Swaps** within the **Kraken Wallet**, therefore it is not enabled on the Kraken Exchange.")
                info("💡 For **Binance**,make sure to have **BNB** in your account in order to minimize the fees.")
        if str_val == 3:
            with container(border=False):
                html("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Submission</h5>""")
                write('First, a **test order** will be created to test if the order is possible based on the trade parameters. If it is not a message with the error from the Exchange API will be shown, otherwise the Trade will be placed.')
                write("You can find ***Open Positions*** and ***Trading History*** in the **Trading Report module**.")
                link_button("Trading Report", "http://localhost:8501/trading_report ", type="primary", icon=":material/youtube_searched_for:")