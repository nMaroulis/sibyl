import streamlit as st
from frontend.src.library.ui_elements import fix_page_layout, set_page_title
from frontend.src.library.strategy_helper.client import get_strategy_metadata, get_strategy_logs
from frontend.src.library.ui_elements import col_style2
import pandas as pd

fix_page_layout('strategy monitor')
set_page_title("Strategy Monitor")
# st.html(col_style2)


strategies = get_strategy_metadata("all")
st.write(strategies)

df = pd.DataFrame(strategies)
st.dataframe(df)

st.button("Pause Strategy", type="secondary", icon=":material/pause_circle:", disabled=True)
st.button("Stop Strategy", type="primary", icon=":material/cancel:")


logs = get_strategy_logs("strategy")
st.write(logs)