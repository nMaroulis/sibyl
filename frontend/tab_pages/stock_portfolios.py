import streamlit as st
import requests
import pandas as pd
import re
from frontend.src.library.stock_analysis_helper.client import fetch_portfolio_senates
from frontend.src.library.ui_elements import fix_page_layout, set_page_title

def parse_amount(amount_str: str) -> float:
    match = re.findall(r"\d{1,3}(?:,\d{3})*", amount_str.replace("$", ""))
    if not match:
        return 0
    values = [int(x.replace(",", "")) for x in match]
    return sum(values) / len(values) if values else 0

# Function to process and aggregate trades
def process_trades(trades):
    df = pd.DataFrame(trades)
    # Keep only relevant columns
    df = df[['senator', 'ticker', 'transaction_date', 'amount', 'type']]
    # Drop rows where ticker is "N/A" or missing
    df = df[df['ticker'].notna() & (df['ticker'] != "N/A")]
    # Convert transaction date to YYYY-MM-DD
    df['transaction_date'] = pd.to_datetime(df['transaction_date'], format="%m/%d/%Y").dt.date
    # Convert amount to numeric mean value
    df['numeric_amount'] = df['amount'].apply(parse_amount)
    df['numeric_amount'] = df['numeric_amount'].astype(int)
    # Aggregate by senator & stock ticker
    aggregated_df = df.groupby(['senator', 'ticker']).agg(
        total_amount=('numeric_amount', 'sum'),
        last_transaction=('transaction_date', 'max')
    ).reset_index()

    # Sort by senator name
    aggregated_df = aggregated_df.sort_values(by=['senator', 'total_amount'], ascending=[True, False])
    # Compute total sum per senator
    senator_totals = aggregated_df.groupby("senator")['total_amount'].sum().reset_index()

    return aggregated_df, senator_totals

# Streamlit UI
fix_page_layout("Stock Portfolio")
set_page_title("U.S. Senate Stock Portfolio Tracker")


with st.spinner("Fetching stock transactions..."):
    trades = fetch_portfolio_senates()

if not trades:
    st.error("Failed to fetch data. Try again later.")
else:
    df, senator_totals = process_trades(trades)

    st.sidebar.header("Filters")
    selected_senator = st.sidebar.selectbox("Select Senator", ["All"] + sorted(df['senator'].unique()))

    # Filter based on selection
    if selected_senator != "All":
        df = df[df['senator'] == selected_senator]

    # Display aggregated stock holdings per senator
    for senator, group in df.groupby("senator"):
        senator_total = senator_totals[senator_totals['senator'] == senator]['total_amount'].values[0]
        st.subheader(f"📌 {senator} (Total: ${senator_total:,.0f})")
        st.table(group[['ticker', 'total_amount', 'last_transaction']])


