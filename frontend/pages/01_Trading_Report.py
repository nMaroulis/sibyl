import streamlit as st
from library.ui_elements import fix_page_layout


fix_page_layout('Report')

st.markdown("""<h2 style='text-align: center;margin-top:0; padding-top:0;'>Trading Report</h2>""", unsafe_allow_html=True)

th_tab, vs_tab = st.tabs(['Trading History', 'Visual Inspection'])

with th_tab:
    st.write('Trading History Report')
with vs_tab:
    st.write('Visual Inspection')
