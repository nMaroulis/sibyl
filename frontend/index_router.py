import streamlit as st

pages = {
    "Your accounts": [
        st.Page("tab_pages/wallet.py", title="Wallet", icon=":material/account_balance_wallet:"),
    ],
    "Trading": [
        st.Page("tab_pages/strategy.py", title="Strategy", icon=":material/strategy:"),
        st.Page("tab_pages/trading_report.py", title="Trading Report", icon=":material/youtube_searched_for:"),
    ],
    "Analytics": [
        st.Page("tab_pages/analytics.py", title="Analytics", icon=":material/query_stats:"),
        st.Page("tab_pages/forecasting.py", title="Forecasting", icon=":material/timeline:"),
        st.Page("tab_pages/explorer.py", title="Blockchain Explorer", icon=":material/explore:"),
    ],
    "News": [
        st.Page("tab_pages/reporting.py", title="Reporting", icon=":material/newspaper:")
    ],
    "Stock Market": [
        st.Page("tab_pages/stock_analysis.py", title="Stock Analysis", icon=":material/monitoring:")
    ],
    "Settings": [
        st.Page("tab_pages/settings.py", title="Settings", icon=":material/settings:")
    ]
}
pg = st.navigation(pages)
pg.run()