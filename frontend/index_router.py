import streamlit as st

pages = {
    "Your accounts": [
        st.Page("pages/00_wallet.py", title="Wallet", icon=":material/account_balance_wallet:"),
    ],
    "Trading": [
        st.Page("pages/01_Strategy.py", title="Strategy", icon=":material/strategy:"),
        st.Page("pages/02_Trading_Report.py", title="Trading Report", icon=":material/youtube_searched_for:"),
    ],
    "Analytics": [
        st.Page("pages/03_Analytics.py", title="Analytics", icon=":material/query_stats:"),
        st.Page("pages/04_Forecasting.py", title="Forecasting", icon=":material/timeline:"),
    ],
    "News": [
        st.Page("pages/05_Reporting.py", title="Reporting", icon=":material/newspaper:")
    ],
    "Settings": [
        st.Page("pages/06_Settings.py", title="Settings", icon=":material/settings:")
    ]
}
pg = st.navigation(pages)
pg.run()