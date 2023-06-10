from streamlit import write, form, form_submit_button, slider, select_slider, text_input, number_input, expander, \
    columns, markdown, caption, selectbox
import time


class GreedyTrader:

    def __init__(self, id=''):
        self.id = id
        self.init_time = None
        self.bet = None

    def __eq__(self):
        return self.id, self.init_time, self.bet

    def get_form(self):
        with form('Greedy Algorithm Form'):
            markdown("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Greedy Strategy Form</h5>""",
                        unsafe_allow_html=True)

            with expander('Trading Parameters', expanded=True):
                bt_cols0 = columns(3)
                with bt_cols0[0]:
                    bet = number_input('Buying Bet [USDT]:', min_value=0.1, max_value=10.0, value=1.0)
                with bt_cols0[1]:
                    stop_loss = number_input('Profit [%]:', min_value=0, max_value=100000, value=0)
                    caption("if option is left to **0**, the **Greediness Level** will define an automatic Profit")
                with bt_cols0[2]:
                    stop_loss = number_input('Stop-Loss [%]:', min_value=0, max_value=100, value=0)
                    caption("if option is left to **0**, the **Greediness Level** will define an automatic Stop Loss")

            bt_cols1 = columns([1,2])
            with bt_cols1[0]:
                selectbox('Time Horizon:', options=['Open', '15 Minutes', '30 Minutes', '1 Hour', '6 Hours', '12 Hours',
                                                    '1 Day', '3 Days', '1 Week', '1 Month', '6 Months'], index=0)
                caption("if option is left to **Open**, the **Greediness Level** will define an automatic Time Horizon")
            with bt_cols1[1]:
                select_slider('Greediness Level:', options=['Very Low', 'Low', 'Moderate', 'High', 'Extreme'], value='Moderate')
                caption("The higher the Greediness level choice is, the Profit Percentage increases, while the Stop Loss decreases, hence the **Higher** the **Risk**.")

            submit = form_submit_button('Initiate Strategy')
            if submit:
                write('OK')
                self.init_time = time.time()
        return 0

    def set_init_time(self, datetime=None):
        self.init_time = datetime
        return 0
