from streamlit import write, metric, columns, markdown, error, cache_data, spinner, info, cache_resource, sidebar,\
    code, session_state, plotly_chart, data_editor, column_config, toggle
from frontend.src.library.overview_helper.client import fetch_account_spot
from frontend.db.db_connector import fetch_fields
from plotly.graph_objects import Figure, Pie, Layout
import plotly.graph_objects as go
from pandas import DataFrame


def get_wallet_balances():
    with spinner('Fetching Wallet Information'):
        data, status_code = fetch_account_spot()
        wallet_list = []
        if status_code == 200:
            if "error" in data:
                error(
                    'Connection to the Exchange API failed. The **current** Exchange API and Secret Keys seem to be ***Invalid***, Please visit the Settings Tab to set a **Valid Exchange API & Secret Key**.')
                return 0
            else:
                # iterate through balances response in order to show them in a table
                pie_chart_labels = []
                pie_chart_values = []
                for coin in data.get('spot_balances'):
                    wallet_list.append([coin, data.get('spot_balances').get(coin).get('free')])
                    pie_chart_labels.append(coin)
                    pie_chart_values.append(float(data.get('spot_balances').get(coin).get('free'))*float(data.get('spot_balances').get(coin).get('price')))  # price in usdt
                    # wallet_list.append([coin, round(data.get('spot_balances').get(coin).get('free'), 4)])  # can add round(data.get('spot_balances').get(coin).get('locked')

                # cols = columns([1,1,1,3])  # max number of spot in the same row
                # c = 0
                # for i in wallet_list:
                #     stk = 0
                #     if i[0][0:2] == 'LD':  # LD prefix means flexible staking
                #         i[0] = i[0][2:]  # remove LD symbol
                #         stk = i[1]
                #     with cols[c]:
                #         if stk == 0:  # if balance is not staked
                #             metric(i[0], i[1])
                #         else:
                #             metric(i[0], i[1], stk)  # if balance is staked
                #     c += 1
                #     if c > 2:
                #         c = 0
                # FIX Staking amounts
                stk = []
                for i in wallet_list:
                    if i[0][0:2] == 'LD':  # LD prefix means flexible staking
                        i[0] = i[0][2:]  # remove LD symbol
                        stk.append(i[1])
                    else:
                        stk.append(0)

                cols = columns(2)  # max number of spot in the same row
                with cols[0]:
                    markdown(
                        """<h6 style='text-align: left;margin-top:1em;'>SPOT Balance</h6>""",
                        unsafe_allow_html=True)

                    wallet_list_df = DataFrame(wallet_list, columns=['Asset', 'SPOT Amount'])
                    wallet_list_df['Staked Amount'] = stk
                    wallet_list_df['Amount in USDT'] = pie_chart_values

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
                    "USDT": "https://cloudfront-us-east-1.images.arcpublishing.com/coindesk/KTF6M73FKBACNI5JQ4S3EW7MRI.png"
                    }

                    wallet_list_df['icon'] = wallet_list_df['Asset'].map(icon_dict).fillna('https://cloudfront-us-east-1.images.arcpublishing.com/coindesk/IKNBTK7JKVEWHGGBKEQMN2HZMM.png')
                    wallet_list_df.insert(0, 'icon', wallet_list_df.pop('icon'))
                    data_editor(wallet_list_df, column_config={"icon": column_config.ImageColumn("")}, hide_index=True,
                                disabled=True, use_container_width=True)

                    toggle('Hide Small Balances')
                with cols[1]:
                    markdown(
                        """<h6 style='text-align: left;margin-top:1em;margin-bottom:0;'></h6>""",unsafe_allow_html=True)

                    # Get Top N
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
                    fig.update_layout(margin= go.layout.Margin(t=0))
                    fig.update_layout(legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1,
                    ))# , margin=dict(l=20, t=20, r=20, b=0)
                    plotly_chart(fig, config=dict(displayModeBar=False), use_container_width=True)
                    markdown('<p style="text-align:center;font-size:5;color:grey">A maximum of 10 Coins can be displayed.</p>', unsafe_allow_html=True)
            info('💡 The locked assets in Binance are not yet available to show.')
        else:
            error("Connection to Backend Server failed. Please visit the Settings Tab to set a **IP** and **PORT**, or check start application manually via the **main.py** script")
    return 0


@cache_data
def get_logo_header():
    # from PIL import Image
    # image = Image.open('./static/home_logo.png')
    # st.image(image, use_column_width=False, width=200)
    # <img src="https://repository-images.githubusercontent.com/648387594/566640d6-e1c4-426d-b2f2-bed885d07e97" style="width:20em;padding-top:0;">
    markdown("""<div align="center">
      <img src="https://repository-images.githubusercontent.com/648387594/3557377e-1c09-45a9-a759-b0d27cf3c501" style="width:20em;padding-top:0;"></div>""", unsafe_allow_html=True)
    # st.markdown("""<h1 style='text-align: center;margin-top:0; padding-top:0;'>Home Page</h1>""", unsafe_allow_html=True)
    return 0


def populate_session_state():
    user_confs = fetch_fields()[0]
    # Populate Session State
    if 'exchange' not in session_state:
        session_state['exchange'] = user_confs[1]
    if 'backend_server_address' not in session_state:
        session_state['backend_server_address'] = user_confs[5]

    with sidebar.popover('Configurations'):
        write('Crypto Exchange:')
        code(user_confs[1], language=None)
        write('Backend Server Address:')
        code(user_confs[5], language=None)
    return 0
