import streamlit as st
from library.ui_elements import fix_padding_top_and_footer
import requests
import plotly.graph_objects as go
from pandas import DataFrame, to_datetime
from plotly.express import imshow


st.set_page_config(layout="wide")
fix_padding_top_and_footer()
st.markdown("""<h1 style='text-align: center;margin-top:0; padding-top:0;'>Trading Report</h1>""", unsafe_allow_html=True)

th_tab, vs_tab = st.tabs(['Trading History', 'Visual Inspection'])

with th_tab:
    st.write('Trading History Report')
with vs_tab:
    st.write('Visual Inspection')
