import streamlit as st

pages = {
    "Your accounts": [
        st.Page("pages/wallet.py", title="Wallet", icon=":material/account_balance_wallet:"),
    ],
    "Trading": [
        st.Page("pages/strategy.py", title="Strategy", icon=":material/strategy:"),
        st.Page("pages/trading_report.py", title="Trading Report", icon=":material/youtube_searched_for:"),
    ],
    "Analytics": [
        st.Page("pages/analytics.py", title="Analytics", icon=":material/query_stats:"),
        st.Page("pages/forecasting.py", title="Forecasting", icon=":material/timeline:"),
        st.Page("pages/explorer.py", title="Blockchain Explorer", icon=":material/explore:"),
    ],
    "News": [
        st.Page("pages/reporting.py", title="Reporting", icon=":material/newspaper:")
    ],
    "Settings": [
        st.Page("pages/settings.py", title="Settings", icon=":material/settings:")
    ]
}
pg = st.navigation(pages)
pg.run()