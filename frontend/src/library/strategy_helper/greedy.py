from streamlit import write, select_slider, number_input, session_state, caption, pills
import time
from frontend.src.library.strategy_helper.client import fetch_trade_info_minimum_order, post_strategy
import re

class GreedyTrader:

    def __init__(self, order_type: str):
        self.chosen_id = None
        self.id = id
        self.init_time = None
        self.bet = None
        self.order_type = order_type.lower()  # make order_type request lower_case
        self.strategy_params = None

    def __eq__(self, **kwargs):
        return self.id, self.init_time, self.bet

    def get_form(self):
        write(
            'The **Greedy** algorithm (or **Scalping**) places a buy order immediately after it is initiated and sells after it has achieved a profit of X%. X is based on the parameters of the algorithm.')
        write('The current **Payoff ratio** based on Trading History using the Greedy Algorithm is *Not Available*')

        strategy_type = pills("Select Greedy algorithm type:", options=['Profit [Percentage]', 'Profit [Absolute Value]', 'Automatic'], default='Profit [Percentage]')

        if strategy_type == "Profit [Percentage]":
            profit = number_input('Profit [%]:', min_value=0.0, max_value=10000.0, value=2.0)
            caption("if option is left to **0**, the **Greediness Level** will define an automatic Profit")
            self.strategy_params = {"type": "profit_percentage", "value": profit}
        elif strategy_type == "Profit [Absolute Value]":
            profit = number_input('Profit:', min_value=0.0, max_value=10000.0, value=0.0)
            caption("if option is left to **0**, the **Greediness Level** will define an automatic Profit")
            self.strategy_params = {"type": "profit_value", "value": profit}
        elif strategy_type == "Automatic":
            alg_type = select_slider('Greediness Level:', options=['Very Low', 'Low', 'Moderate', 'High', 'Extreme'], value='Moderate')
            caption("The higher the Greediness level choice is, the Profit Percentage increases, while the Stop Loss decreases, hence the **Higher** the **Risk**.")
            self.strategy_params = {"type": "auto", "value": alg_type}
        else:
            write("Invalid Option")

        return 0


    def submit_strategy(self):
        res = post_strategy(exchange=session_state['trade_exchange_api'].lower().replace(" ", "_"), from_coin=session_state['from_coin'], to_coin=session_state['target_coin'],
                            from_amount=session_state['buy_amount'], strategy='greedy', strategy_params=self.strategy_params,
                            order_type=self.order_type)
        self.init_time = time.time()
        return res

    def set_init_time(self, datetime=None):
        self.init_time = datetime
        return 0
