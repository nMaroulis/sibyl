from streamlit import write, form, form_submit_button, slider, select_slider, text_input, number_input, expander, \
    columns, session_state, caption, selectbox, spinner, success, error, rerun, toast
import time
from frontend.src.library.strategy_helper.client import fetch_trade_info_minimum_order, send_strategy
from frontend.src.library.crypto_dictionary_assistant import get_crypto_coin_dict


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
            # markdown("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Greedy Strategy Form</h5>""",
            #             unsafe_allow_html=True)
            #
            # with expander('Trading Parameters', expanded=True):
            #     bt_cols0 = columns(3)
            #     with bt_cols0[0]:
            #         bet = number_input('Buying Bet [USDT]:', min_value=1.0, max_value=100000.0, value=50.0)
            #     with bt_cols0[1]:
            #         stop_loss = number_input('Profit [%]:', min_value=0, max_value=100000, value=0)
            #         caption("if option is left to **0**, the **Greediness Level** will define an automatic Profit")
            #     with bt_cols0[2]:
            #         stop_loss = number_input('Stop-Loss [%]:', min_value=0, max_value=100, value=0)
            #         caption("if option is left to **0**, the **Greediness Level** will define an automatic Stop Loss")
            # crypto_list = list(get_crypto_coin_dict().values())
            # crypto_list.sort()
            # crypto_list.insert(0, 'Auto')
            # target_coin = selectbox('Crypto Asset:', options=crypto_list, index=6)

            bt_cols1 = columns([1, 2])
            with bt_cols1[0]:
                custom_profit = number_input('Profit [%]:', min_value=0, max_value=100000, value=0)
                caption("if option is left to **0**, the **Greediness Level** will define an automatic Profit")
            with bt_cols1[1]:
                strategy_type = select_slider('Greediness Level:', options=['Very Low', 'Low', 'Moderate', 'High', 'Extreme'], value='Moderate')
                caption("The higher the Greediness level choice is, the Profit Percentage increases, while the Stop Loss decreases, hence the **Higher** the **Risk**.")

            submit = form_submit_button('Initiate Strategy')
            if submit:
                with spinner('Sending Strategy to Server....'):
                    # pair_symbol = session_state['target_coin']+'USDT'
                    # min_order_limit = fetch_trade_info_minimum_order(pair_symbol)
                    # print(min_order_limit)
                    # if session_state['buy_amount'] >= min_order_limit:
                    #     success("The **Minimum buy order Limit** of **" + str(min_order_limit) + "** for the " + pair_symbol + " is satisfied!")
                    res = send_strategy(from_coin='USDT', to_coin=session_state['target_coin'], from_amount=session_state['buy_amount'], strategy='greedy:'+strategy_type, order_type=self.order_type)
                    if "error" in res:
                        error('Server Response ' + str(res))
                        toast('⛔ Trade was NOT Executed!')
                    else:
                        toast('✅ Trade was successfully Executed!')
                        success('Server Response ' + str(res))
                        with spinner('Refreshing Page:'):
                            time.sleep(4)
                            rerun()
                    # else:
                    #     error("The **Minimum Buy Order Limit** of **" + str(min_order_limit) + "** for the " + pair_symbol + " is NOT satisfied.")
                    #     toast('⛔ Please raise the Buy Order Amount!')

                    self.init_time = time.time()
        return 0

    def set_init_time(self, datetime=None):
        self.init_time = datetime
        return 0
