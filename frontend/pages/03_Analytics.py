import streamlit as st
from frontend.src.library.ui_elements import fix_page_layout
from frontend.src.library.analytics_helper.ui_elements import get_price_history_form, get_correlation_heatmap_form

fix_page_layout('Analytics')
st.markdown("""<h2 style='text-align: center;margin-top:0; padding-top:0;'>Analytics</h2>""", unsafe_allow_html=True)

ph_tab, ch_tab, cs_tab = st.tabs(['Price History', 'Correlation Heatmap', 'Causality Test'])
with ph_tab:  # Price History
    get_price_history_form()
with ch_tab:  # Correlation Heatmap
    get_correlation_heatmap_form()
with cs_tab:
    st.markdown("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Granger Causality Test</h5>""",
             unsafe_allow_html=True)
    st.warning('Not yet Supported ⚠️')
