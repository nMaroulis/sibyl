import pandas as pd
import streamlit as st
from frontend.src.library.wallet_helper.client import fetch_account_spot


def get_spot_balance_wallet_table(exchange: str, quote_pair_asset: str = None) -> None:

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
    # Convert to DataFrame and rename columns
    df = pd.DataFrame.from_dict(data["spot_balances"], orient="index").reset_index()
    df.columns = ["Asset", "Available SPOT", "Locked", "Amount in Quote"]
    print(df.dtypes)
    # Calc the amount in quote
    if quote_pair_asset is not None:
        df["Amount in Quote"] = df["Amount in Quote"] * (df["Available SPOT"] + df["Locked"])
    df['icon'] = df['Asset'].map(icon_dict).fillna(
        'https://cloudfront-us-east-1.images.arcpublishing.com/coindesk/IKNBTK7JKVEWHGGBKEQMN2HZMM.png')
    df.insert(0, 'icon', df.pop('icon'))
    df.sort_values(by=['Asset'], inplace=True)

    # save to session state
    st.session_state[f"{exchange}_account_balance"] = dict(zip(df['Asset'], df['Available SPOT']))


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
