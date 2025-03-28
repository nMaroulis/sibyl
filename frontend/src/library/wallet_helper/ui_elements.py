import pandas as pd
import streamlit as st
from frontend.src.library.wallet_helper.client import fetch_account_spot, fetch_account_information
from plotly.graph_objects import Figure, Pie
import plotly.graph_objects as go


def fetch_and_parse_spot_balance(exchange: str, quote_pair_asset: str = None) -> pd.DataFrame | None:
    icon_dict = {
        "BTC": "https://cloudfront-us-east-1.images.arcpublishing.com/coindesk/S3ODTTWSMFCFTJZD3K5K5OX5HI.png",
        "ETH": "https://cloudfront-us-east-1.images.arcpublishing.com/coindesk/ZJZZK5B2ZNF25LYQHMUTBTOMLU.png",
        "BNB": "https://cloudfront-us-east-1.images.arcpublishing.com/coindesk/NUFAYV4HABB4PFLXBNPXATMI3A.png",
        "XRP": "https://cloudfront-us-east-1.images.arcpublishing.com/coindesk/2MGMNAZL7FDERJ7OLMVBWXK55Q.png",
        "ADA": "https://cloudfront-us-east-1.images.arcpublishing.com/coindesk/6US2A64CB5HLBDLUCVKUHVAN44.png",
        "SOL": "https://cloudfront-us-east-1.images.arcpublishing.com/coindesk/VNKJKO74VFFNTBJF7BP4N4YHWI.png",
        "LTC": "https://cloudfront-us-east-1.images.arcpublishing.com/coindesk/RSA3NC7WINGZXP2VE2Z34XPEZI.png",
        "BUSD": "https://cloudfront-us-east-1.images.arcpublishing.com/coindesk/NW5MWYONWVDXJP2M2D66JKKRAY.png",
        "TRX": "https://cloudfront-us-east-1.images.arcpublishing.com/coindesk/DTNQWV2C3ZDRVMK6UTPUT73N3I.png",
        "LINK": "https://cloudfront-us-east-1.images.arcpublishing.com/coindesk/M2MXO2LRPNHXRLRGGKQW77CU3A.png",
        "DOT": "https://cloudfront-us-east-1.images.arcpublishing.com/coindesk/FCVVAWNXP5AXLP4IEVIQHD6XIY.png",
        "USDT": "https://cloudfront-us-east-1.images.arcpublishing.com/coindesk/KTF6M73FKBACNI5JQ4S3EW7MRI.png",
        "DOGE": "https://resources.cryptocompare.com/asset-management/26/1662541306654.png",
        "USDC": "https://resources.cryptocompare.com/asset-management/14/1728310128919.png"
    }

    # pd.set_option('float_format', '{:f}'.format)
    # Fetch Data from Exchange Client
    data = fetch_account_spot(exchange, quote_pair_asset)
    if data:
        # Convert to DataFrame and rename columns
        df = pd.DataFrame.from_dict(data["spot_balances"], orient="index").reset_index()
        df.columns = ["Asset", "Available SPOT", "Locked", "Amount in Quote"]
        # Calc the amount in quote
        if quote_pair_asset is not None:
            df["Amount in Quote"] = df["Amount in Quote"] * (df["Available SPOT"] + df["Locked"])
        df['icon'] = df['Asset'].map(icon_dict).fillna(
            'https://cloudfront-us-east-1.images.arcpublishing.com/coindesk/IKNBTK7JKVEWHGGBKEQMN2HZMM.png')
        df.insert(0, 'icon', df.pop('icon'))
        df.sort_values(by=['Asset'], inplace=True)

        # save to session state
        st.session_state[f"{exchange}_account_balance"] = dict(zip(df['Asset'], df['Available SPOT']))

        return df
    else:
        return None

def get_spot_balance_wallet_table(exchange: str, quote_pair_asset: str = None) -> None:
    with st.spinner('Fetching Wallet Balance Information...'):

        df = fetch_and_parse_spot_balance(exchange, quote_pair_asset)
        if df is not None:
            if quote_pair_asset is None:
                quote_pair_asset = "N/A"

            wallet_html = f"""
            <style>
                .wallet-container {{
                    background-color: #343434;
                    padding: 20px;
                    border-radius: 10px;
                    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.6);
                    max-height: 600px;
                    overflow-y: auto;
                }}
                .wallet-title {{
                    font-size: 18px;
                    font-weight: bold;
                    color: #FFD700;
                    margin-bottom: 15px;
                }}
                .wallet-table {{
                    width: 100%;
                    border-collapse: collapse;
                }}
                .wallet-table th {{
                    font-weight: bold;
                    padding: 12px;
                    color: #ffffff;
                    font-size: 16px;
                    border-bottom: 2px solid #FFD700;
                    text-align: left;
                }}
                .wallet-table td {{
                    padding: 10px;
                    text-align: left;
                    border-bottom: 1px solid rgba(255, 255, 255, 0.2);
                }}
                .wallet-table img {{
                    width: 30px;
                    height: 30px;
                    vertical-align: middle;
                }}
                .asset-name {{
                    color: #ffffff;
                    font-weight: bold;
                }}
                .spot-amount {{
                    color: #1E90FF;
                    font-weight: bold;
                }}
                .staked-amount {{
                    color: #32CD32;
                    font-weight: bold;
                }}
                .quote-amount {{
                    color: #FFA500;
                    font-weight: bold;
                }}
            </style>
        
            <div class="wallet-container">
                <div class="wallet-title">SPOT Balance</div>
                <table class="wallet-table">
                    <thead>
                        <tr>
                            <th>Asset</th>
                            <th>SPOT Amount</th>
                            <th>Locker/Staked Amount</th>
                            <th>Amount in {quote_pair_asset}</th>
                        </tr>
                    </thead>
                    <tbody>
                        """ + "".join([
                f"""
                            <tr>
                                <td class='asset-name'><img src='{row['icon']}' alt='{row['Asset']}'> {row['Asset']}</td>
                                <td class='spot-amount'>{row['Available SPOT']}</td>
                                <td class='staked-amount'>{row['Locked']}</td>
                                <td class='quote-amount'>{row['Amount in Quote']} {quote_pair_asset}</td>
                            </tr>
                            """ for _, row in df.iterrows()
            ]) + f"""
                    </tbody>
                </table>
                <div class="wallet-title">Total Balance: <span class='quote-amount'>{round(df['Amount in Quote'].sum(), 2)} {quote_pair_asset}</span></div>
            </div>
            """

            st.html(wallet_html)
            if exchange == "Coinbase Sandbox":
                st.info('💡 Price in Quote asset is calculated using the Coinbase API, since the Sandbox contains limited markets.')
        else:
            st.error("Failed to fetch Account Spot Balance. Check logs.", icon=":material/warning:")


def get_pie_chart(exchange: str, quote_pair_asset: str = None) -> None:

    df = fetch_and_parse_spot_balance(exchange, quote_pair_asset)
    if df is not None:
        pie_chart_labels = []
        pie_chart_values = []
        for _, row in df.iterrows():
            pie_chart_labels.append(row["Asset"])
            pie_chart_values.append(row["Amount in Quote"])

        if len(pie_chart_values) > 10:
            label_value_pairs = list(zip(pie_chart_labels, pie_chart_values))
            sorted_pairs = sorted(label_value_pairs, key=lambda x: x[1], reverse=True)
            top_n_pairs = sorted_pairs[:10]
            top_n_labels, top_n_values = zip(*top_n_pairs)
            top_n_labels = top_n_labels + ('Other',)
            top_n_values = top_n_values + (sum(pie_chart_values) - sum(top_n_values),)
        else:
            top_n_labels, top_n_values = pie_chart_labels, pie_chart_values

        fig = Figure(data=[Pie(labels=top_n_labels, values=top_n_values, hole=0.6, textinfo='percent')])
        fig.update_layout(margin=go.layout.Margin(t=20))
        fig.update_layout(legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
        ))  # , margin=dict(l=20, t=20, r=20, b=0)
        st.plotly_chart(fig, config=dict(displayModeBar=False), use_container_width=True)
        st.html('<p style="text-align:center;font-size:5;color:grey">A maximum of 10 Assets can be displayed.</p>')


@st.cache_data
def get_logo_header() -> None:
    st.html("""<div align="center">
      <img src="https://repository-images.githubusercontent.com/648387594/3557377e-1c09-45a9-a759-b0d27cf3c501" style="width:20em;padding-top:0;"></div>""")


def get_account_information(exchange: str) -> None:

    # Sample Binance commission data
    data = fetch_account_information(exchange)

    # HTML & CSS for stylish UI
    html_code = f"""
    <style>
        .exchange-card {{
            max-width: 100%;
            padding: 20px;
            background: linear-gradient(135deg, #1e1e1e, #262626);
            border-radius: 15px;
            box-shadow: 0px 4px 15px rgba(255, 215, 0, 0.3);
            font-family: 'Arial', sans-serif;
            color: #f0f0f0;
            text-align: left;
            margin: auto;
        }}
        .exchange-header {{
            font-size: 20px;
            font-weight: bold;
            text-align: center;
            padding-bottom: 10px;
            border-bottom: 2px solid rgba(255, 215, 0, 0.6);
        }}
        .commission-item {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            font-size: 16px;
        }}
        .label {{
            font-weight: bold;
            color: #FFD700;
        }}
        .value {{
            color: #f0f0f0;
        }}
        .trade-status {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            font-size: 16px;
        }}
        .status-true {{
            color: #32CD32; /* Green */
            font-weight: bold;
        }}
        .status-false {{
            color: #FF4500; /* Red */
            font-weight: bold;
        }}
    </style>

    <div class="exchange-card">
        <div class="exchange-header">{exchange} Account Info</div>
        <div class="commission-item">
            <span class="label">Maker Commission:</span>
            <span class="value">{data['maker_commission']} %</span>
        </div>
        <div class="commission-item">
            <span class="label">Taker Commission:</span>
            <span class="value">{data['taker_commission']} %</span>
        </div>
        <div class="commission-item">
            <span class="label">Buyer Commission:</span>
            <span class="value">{data['buyer_commission']} %</span>
        </div>
        <div class="commission-item">
            <span class="label">Seller Commission:</span>
            <span class="value">{data['seller_commission']} %</span>
        </div>
        <div class="trade-status">
            <span class="label">Can Trade:</span>
            <span class="{'status-true' if data['can_trade'] else 'status-false'}">{'✔ Yes' if data['can_trade'] else '✖ No'}</span>
        </div>
        <div class="trade-status">
            <span class="label">Can Deposit:</span>
            <span class="{'status-true' if data['can_deposit'] else 'status-false'}">{'✔ Yes' if data['can_deposit'] else '✖ No'}</span>
        </div>
        <div class="trade-status">
            <span class="label">Can Withdraw:</span>
            <span class="{'status-true' if data['can_withdraw'] else 'status-false'}">{'✔ Yes' if data['can_withdraw'] else '✖ No'}</span>
        </div>
    </div>
    """

    st.html(html_code)
    with st.popover("What are these information?", icon=":material/contact_support:"):
        instructions_markdown = """
            ## 📌 Understanding Maker-Taker Fees & BPS  
            
            ### 🎯 What Are Maker & Taker Fees?  
            
            In cryptocurrency exchanges like Binance, trading fees are typically categorized as **maker** or **taker** fees:  
            
            - **Maker Fee** 🏗️: Applies when you add liquidity to the order book (e.g., placing a limit order that isn’t immediately matched).  
            - **Taker Fee** ⚡: Applies when you remove liquidity from the order book (e.g., placing a market order that gets executed instantly).  
            
            💡 **Key Difference:**  
            - Makers help **stabilize** prices by adding orders, often receiving lower fees.  
            - Takers provide **instant** transactions but pay higher fees.  
            
            ---
            
            ### 📉 What Does BPS (Basis Points) Mean?  
            
            BPS, or **basis points**, is a unit used to describe **percentage-based fees** in finance and trading.  
            - **1 BPS = 0.01%**  
            - **100 BPS = 1%**  
            
            #### 🔢 Example:  
            If a trading fee is **10 BPS**, it means:  
            ```math
            10 BPS = 10 × 0.01% = 0.10% fee per trade
        """
        st.markdown(instructions_markdown)
