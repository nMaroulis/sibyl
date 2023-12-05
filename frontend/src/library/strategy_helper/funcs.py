from extra_streamlit_components import stepper_bar
from streamlit import write, container, expander, info, markdown


def get_strategy_instructions():

    with expander('Trading Instructions', expanded=True):
        str_val = stepper_bar(steps=["Trading Options", "Asset Options", "Algorithm & Parameters", "Submission"], lock_sequence=False)

        if str_val == 0:
            with container(border=False):
                markdown("""<h4 style='text-align: left;margin-top:0; padding-top:0;'>Trading & Convert</h4>""",
                            unsafe_allow_html=True)
                write("The Binance **Convert** API enables trading with **0 fees**. If the backend server doesn't find a valid Convert API, the standard buy/sell order will be used. In that case make sure to have BNB in your account in order to minimize the fees.")
                write("Check if you are eligible for the Convert functionality in the sidebar 👈.")
                info("💡 Make sure to have BNB in your account in order to minimize the fees.")

        if str_val == 1:
            with container(border=False):
                write('BBBBBBBBB')
        if str_val == 2:
            with container(border=False):
                write('CCCCCCCCCCC')
        if str_val == 3:
            with container(border=False):
                write('DDDDDDDDDDD')
