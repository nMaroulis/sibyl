import streamlit as st
from frontend.src.utils.ui_elements import fix_page_layout, set_page_title
from frontend.src.utils.analytics_helper.ui_elements import get_correlation_heatmap_form, get_price_analytics_form
from frontend.src.utils.settings_helper.navigation import exchange_api_status_check
from frontend.src.utils.oracle.ui_elements import oracle_button


fix_page_layout('Analytics')
set_page_title('Analytics')


if "available_exchange_apis" not in st.session_state:
    with st.spinner("Checking API Availability Status..."):
        exchange_api_status_check()


ph_tab, ch_tab, cs_tab = st.tabs(['Price History', 'Correlation Heatmap', 'Causality Test'])
with ph_tab:  # Price History Analysis
    get_price_analytics_form()
with ch_tab:  # Correlation Heatmap
    get_correlation_heatmap_form()
with cs_tab:
    st.markdown("""<h5 style='text-align: left;margin-top:0; padding-top:0;'>Granger Causality Test</h5>""",
             unsafe_allow_html=True)
    st.warning('Not yet Supported ⚠️')


# ========================
# ORACLE
# ========================
oracle_button(module="analytics", enabled=False)
