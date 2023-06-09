from streamlit import write, form, form_submit_button, slider, select_slider, text_input, number_input, expander, \
    columns, markdown, caption, selectbox, spinner, success, error, experimental_rerun
import time
from library.strategy_helper.client import fetch_trade_info_minimum_order, send_strategy
from library.crypto_dictionary_assistant import get_crypto_coin_dict


class GreedyTrader:

    def __init__(self, order_type='Swap'):
        self.id = id
        self.init_time = None
        self.bet = None
        self.order_type = order_type.lower()  # make order_type request lower_case

    def __eq__(self):
        return self.id, self.init_time, self.bet

    def get_form(self):
        with form('Greedy Algorithm Form'):
            markdown("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Greedy Strategy Form</h5>""",
                        unsafe_allow_html=True)

            with expander('Trading Parameters', expanded=True):
                bt_cols0 = columns(3)
                with bt_cols0[0]:
                    bet = number_input('Buying Bet [USDT]:', min_value=1.0, max_value=100000.0, value=50.0)
                with bt_cols0[1]:
                    stop_loss = number_input('Profit [%]:', min_value=0, max_value=100000, value=0)
                    caption("if option is left to **0**, the **Greediness Level** will define an automatic Profit")
                with bt_cols0[2]:
                    stop_loss = number_input('Stop-Loss [%]:', min_value=0, max_value=100, value=0)
                    caption("if option is left to **0**, the **Greediness Level** will define an automatic Stop Loss")
            crypto_list = list(get_crypto_coin_dict().values())
            crypto_list.sort()
            crypto_list.insert(0, 'Auto')
            target_coin = selectbox('Crypto Asset:', options=crypto_list, index=6)

            bt_cols1 = columns([1, 2])
            with bt_cols1[0]:
                selectbox('Time Horizon:', options=['Open', '15 Minutes', '30 Minutes', '1 Hour', '6 Hours', '12 Hours',
                                                    '1 Day', '3 Days', '1 Week', '1 Month', '6 Months'], index=0)
                caption("if option is left to **Open**, the **Greediness Level** will define an automatic Time Horizon")
            with bt_cols1[1]:
                strategy_type = select_slider('Greediness Level:', options=['Very Low', 'Low', 'Moderate', 'High', 'Extreme'], value='Moderate')
                caption("The higher the Greediness level choice is, the Profit Percentage increases, while the Stop Loss decreases, hence the **Higher** the **Risk**.")

            submit = form_submit_button('Initiate Strategy')
            if submit:
                with spinner('Checking Strategy Validity...'):
                    pair_symbol = target_coin+'USDT'
                    min_order_limit = fetch_trade_info_minimum_order(pair_symbol)
                    print(min_order_limit)
                    if bet >= min_order_limit:
                        success("The **Minimum buy order Limit** of **" + str(min_order_limit) + "** for the " + pair_symbol + " is satisfied!")
                        write("sending Strategy to Server.")
                        res = send_strategy(from_coin='USDT', to_coin=target_coin, from_amount=bet, strategy='greedy:'+strategy_type, order_type=self.order_type)
                        if "error" in res:
                            error('Server Response ' + str(res))
                        else:
                            success('Server Response ' + str(res))
                            with spinner('Refreshing Page:'):
                                time.sleep(4)
                                experimental_rerun()
                    else:
                        error("The **Minimum Buy Order Limit** of **" + str(min_order_limit) + "** for the " + pair_symbol + " is NOT satisfied.")
                    self.init_time = time.time()
        return 0

    def set_init_time(self, datetime=None):
        self.init_time = datetime
        return 0
