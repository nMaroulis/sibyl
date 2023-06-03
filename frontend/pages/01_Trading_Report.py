import streamlit as st
import requests
import plotly.graph_objects as go
from pandas import DataFrame, to_datetime
from plotly.express import imshow


st.set_page_config(layout="wide")

st.header("Trading Report")

th_tab, vs_tab = st.tabs(['Trading History', 'Visual Inspection'])

with th_tab:
    st.write('Trading History Report')
with vs_tab:
    st.write('Visual Inspection')
