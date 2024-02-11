from streamlit import write, form, form_submit_button, button, select_slider, number_input, \
    columns, session_state, caption, spinner, success, error, rerun, toast, divider
import time
from frontend.src.library.strategy_helper.client import fetch_trade_info_minimum_order, send_strategy

class GreedyTrader:

    def __init__(self, order_type='Swap'):
        self.chosen_id = None
        self.id = id
        self.init_time = None
        self.bet = None
        self.order_type = order_type.lower()  # make order_type request lower_case

    def __eq__(self):
        return self.id, self.init_time, self.bet

    def get_form(self):
        write(
            'The **Greedy** algorithm (or **Scalping**) places a buy order immediately after it is initiated and sells after it has achieved a profit of X%. X is based on the parameters of the algorithm.')
        write('The current **Payoff ratio** based on Trading History using the Greedy Algorithm is *Not Available*')

        from extra_streamlit_components import tab_bar, TabBarItemData

        self.chosen_id = tab_bar(data=[
            TabBarItemData(id=1, title="Automatic", description="Choose Level"),
            TabBarItemData(id=2, title="Profit", description="Percentage"),
            TabBarItemData(id=3, title="Profit", description="Absolute Value"),
        ], default=1)

        bt_cols1 = columns([1, 2])
        if self.chosen_id == "1":
            self.custom_profit = number_input('Profit [%]:', min_value=0.0, max_value=10000.0, value=0.0)
            caption("if option is left to **0**, the **Greediness Level** will define an automatic Profit")
        elif self.chosen_id == "2":
            self.strategy_type = select_slider('Greediness Level:', options=['Very Low', 'Low', 'Moderate', 'High', 'Extreme'], value='Moderate')
            caption("The higher the Greediness level choice is, the Profit Percentage increases, while the Stop Loss decreases, hence the **Higher** the **Risk**.")
        else:
            self.strategy_type = select_slider('Greediness Level:', options=['Very Low', 'Low', 'Moderate', 'High', 'Extreme'], value='Moderate')
            caption("The higher the Greediness level choice is, the Profit Percentage increases, while the Stop Loss decreases, hence the **Higher** the **Risk**.")

        return 0

    def submit_strategy(self):
        res = send_strategy(from_coin=session_state['from_coin'], to_coin=session_state['target_coin'],
                            from_amount=session_state['buy_amount'], strategy='greedy:' + self.strategy_type,
                            order_type=self.order_type)
        self.init_time = time.time()
        return res

    def set_init_time(self, datetime=None):
        self.init_time = datetime
        return 0
