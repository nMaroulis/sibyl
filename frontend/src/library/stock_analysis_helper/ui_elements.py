import streamlit as st
from frontend.src.library.stock_analysis_helper.client import fetch_stock_details
import re
from frontend.src.library.stock_analysis_helper.plots import risk_gauge, linear_gauge_chart


def extract_symbol(stock_string) -> str | None:

    match = re.search(r"\[(.*?)\]", stock_string)
    return match.group(1) if match else None


def display_company_info(info: dict, stock_symbol: str):
    # st.html(col_style2)
    st.title(":material/badge: " + info.get("longName", "Company Information"))
    st.html("</br>")
    c0, c1, c2 = st.columns(3)
    with c0:
        st.write(":material/id_card: Stock symbol: {}".format(stock_symbol))
        st.write(f":material/link: **Website:** [Visit Website]({info.get('website', 'N/A')})")
    with c1:
        st.write(f":material/domain: **Industry:** {info.get('industryDisp', 'N/A')}")
        st.write(f":material/domain_add: **Sector:** {info.get('sectorDisp', 'N/A')}")
    with c2:
        st.write(f":material/pin_drop: **Country:** {info.get('country', 'N/A')}")
        st.write(f":material/person_apron: **Employees:** {info.get('fullTimeEmployees', 'N/A')}")

    st.html("</br>")
    st.subheader("Market Data")
    c0, c1, c2 = st.columns(3)
    with c0:
        st.metric("Current Price", str(info.get('currentPrice'))+"$")  if "currentPrice" in info else st.metric("Current Price", "N/A", border=True)
    with c1:
        st.metric("Market Cap", f'{info.get('marketCap'):,}$')  if "marketCap" in info else st.metric("Market Cap", "N/A")
    with c2:
        st.metric("Enterprise Value", f'{info.get('enterpriseValue'):,}$')  if "enterpriseValue" in info else st.metric("Enterprise Value", "N/A")

    # st.write(
    #     f"**Headquarters:** {info.get('address1', 'N/A')}, {info.get('city', 'N/A')}, {info.get('state', 'N/A')}, {info.get('zip', 'N/A')}, {info.get('country', 'N/A')}")
    # st.write(f"**Phone:** {info.get('phone', 'N/A')}")

    # Financial Health Section
    # Create columns for market data and financial metrics
    st.html("</br>")
    st.subheader("Financial Metrics")
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Beta:** {info.get('beta', 'N/A')}")
        st.write(f"**Trailing P/E:** {info.get('trailingPE', 'N/A')}")
        st.write(f"**Forward P/E:** {info.get('forwardPE', 'N/A')}")
        st.write(f"**Price to Sales (TTM):** {info.get('priceToSalesTrailing12Months', 'N/A')}")
    with col2:
        st.write(f"**Price to Book:** {info.get('priceToBook', 'N/A')}")
        st.write(f"**Profit Margin:** {info.get('profitMargins', 'N/A')}%")
        st.write(f"**Operating Margin:** {info.get('operatingMargins', 'N/A')}%")

    # Dividend & Cash Flow Section
    st.html("</br>")
    st.subheader("Dividends & Cash Flow")
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Dividend Rate:** ${info.get('dividendRate', 'N/A')}")
        st.write(f"**Dividend Yield:** {info.get('dividendYield', 'N/A')}%") #  * 100:.2f
        st.write(f"**Last Dividend Date:** {info.get('lastDividendDate', 'N/A')}")
    with col2:
        st.write(f"**Free Cash Flow:** ${info.get('freeCashflow', 'N/A')}")
        st.write(f"**Operating Cash Flow:** ${info.get('operatingCashflow', 'N/A')}")


    # Risk Section
    st.header("Risk & Governance")

    c0, c1, c2, c3, c4 = st.columns(5)
    with c0:
        st.write("Overall risk")
        st.pyplot(risk_gauge(info.get('overallRisk'))) if 'overallRisk' in info else st.write("N/A")
    with c1:
        st.write("Audit risk")
        st.pyplot(risk_gauge(info.get('auditRisk'))) if 'auditRisk' in info else st.write("N/A")
    with c2:
        st.write("Board risk")
        st.pyplot(risk_gauge(info.get('boardRisk'))) if 'boardRisk' in info else st.write("N/A")
    with c3:
        st.write("Compensation risk")
        st.pyplot(risk_gauge(info.get('compensationRisk'))) if 'compensationRisk' in info else st.write("N/A")
    with c4:
        st.write("Shareholder Rights risk")
        st.pyplot(risk_gauge(info.get('shareHolderRightsRisk'))) if 'shareHolderRightsRisk' in info else st.write("N/A")

    # Leadership Section
    st.header("Leadership Team")
    exp = True
    for officer in info.get("companyOfficers", []):
        with st.expander(f"{officer.get('title', 'N/A')}", expanded=exp):
            st.subheader(f"{officer.get('name', 'N/A')} - {officer.get('title', 'N/A')}")
            st.write(
                f"**Age:** {officer.get('age', 'N/A')} | **Total Pay (FY 2024):** ${officer.get('totalPay', 'N/A')}")
        exp = False

    # Stock Performance Section
    st.header("Stock Performance & Forecasts")
    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**52 Week High:** ${info.get('fiftyTwoWeekHigh', 'N/A')}")
        st.write(f"**52 Week Low:** ${info.get('fiftyTwoWeekLow', 'N/A')}")
    with col2:
        st.write(f"**Target Mean Price:** ${info.get('targetMeanPrice', 'N/A')}")

    st.subheader("Yahoo Finance Analyst Opinions")
    st.write(f"{info.get('numberOfAnalystOpinions', 'N/A')} **Analysts** generated the following recommendation **{info.get('recommendationKey', 'N/A')}** with a score of **{info.get('recommendationMean', 'N/A')}**.")
    # st.write(f"**Recommended Action**:")
    # st.html(f"""<h2 style="color:blue;margin:0">{info.get('recommendationKey', 'N/A')}</h2>""")
    c0, _, _ = st.columns(3)
    with c0:
        st.pyplot(linear_gauge_chart(1.4))


def get_stock_analysis(stock_symbol: str):
    symbol = extract_symbol(stock_symbol)
    if symbol is None:
        st.error("Invalid stock symbol", icon=":material/error:")
    stock_details = fetch_stock_details(symbol)
    # write(get_stock_details(symbol))

    display_company_info(stock_details["info"], symbol)