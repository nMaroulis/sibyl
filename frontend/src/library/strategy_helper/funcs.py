from extra_streamlit_components import stepper_bar
from streamlit import write, container, expander, html, link_button


def get_strategy_instructions(exp=False):

    with expander('📖 Trading Instructions', expanded=exp):
        str_val = stepper_bar(steps=["Asset Options", "Trading Options", "Algorithm & Parameters", "Submission"], lock_sequence=False)

        if str_val == 0:
            with container(border=False):
                html("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Asset Options</h5>""")
                write("TBA")
        if str_val == 1:
            with container(border=False):
                html("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Trading & Convert</h5>""")
                write("TBA")
        if str_val == 2:
            with container(border=False):
                html("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Algorithm & Parameters</h5>""")
                write('TBA')
        if str_val == 3:
            with container(border=False):
                html("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Submission</h5>""")
                write('After the Strategy is submitted, it will be parsed and sent to the Exchange API. If it is successful you can track its progress in the Trading Report module.')
                link_button("Trading Report", "http://localhost:8501/trading_report ", type="primary", icon=":material/youtube_searched_for:")