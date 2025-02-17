import streamlit as st
from frontend.db.stocks_db_client import get_stocks_list
from frontend.src.library.stock_analysis_helper.ui_elements import get_stock_analysis
from frontend.src.library.ui_elements import fix_page_layout


fix_page_layout('📈Stock Market')
st.html("""<h2 style='text-align: center;margin-top:0; padding-top:0;'>Stock Market Analysis</h2>""")

st.write(
    "Choose the Company you want in order to get all the information available. Once the company is chosen, the Stock Market Analysis page will display all the information regarding the company and its stock. The advisor tab, using AI and financial formulas and algorithms will determine if the company's stock is worth buying.")

if "selected_stock" not in st.session_state:
    stocks = get_stocks_list()
    with st.form(key="stocks_form", clear_on_submit=False):
        selected_stock = st.selectbox("Select a Stock to Analyze", stocks, placeholder="Find a Stock", index=None)
        sub_button = st.form_submit_button(label="Generate Analysis", icon=":material/query_stats:")
        if sub_button:
            if selected_stock is None:
                st.warning("You must select a stock to analyze", icon=":material/warning:")
            else:
                st.session_state.selected_stock = selected_stock
                st.write(selected_stock)
                st.rerun()
else:
    if st.sidebar.button("Reset Analysis", type="primary", use_container_width=True, icon=":material/restart_alt:"):
        del st.session_state.selected_stock
        st.rerun()
    with st.spinner("Fetching Stock Data..."):
        get_stock_analysis(st.session_state.selected_stock)
