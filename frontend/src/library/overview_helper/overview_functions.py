import requests
from streamlit import write, metric, columns, markdown, error, cache_data, spinner, warning


def get_wallet_balances():
    write('SPOT')
    with spinner('Fetching Wallet Information'):
        url = "http://127.0.0.1:8000/accountant/account/spot/overview"
        response = requests.get(url)
        data = response.json()
        wallet_list = []
        if response.status_code == 200:
            if "error" in data:
                error(
                    'Connection to the Exchange API failed. The **current** Exchange API and Secret Keys seem to be ***Invalid***, Please visit the Settings Tab to set a **Valid Exchange API & Secret Key**.')
                return 0
            else:
                for coin in data.get('spot_balances'):
                    wallet_list.append([coin, round(data.get('spot_balances').get(coin).get('free'), 4)])  # can add round(data.get('spot_balances').get(coin).get('locked')

                cols = columns(6)  # max number of spot in the same row
                c = 0
                for i in wallet_list:
                    stk = 0
                    if i[0][0:2] == 'LD':  # LD prefix means flexible staking
                        i[0] = i[0][2:]  # remove LD symbol
                        stk = i[1]
                    with cols[c]:
                        if stk == 0:  # if balance is not staked
                            metric(i[0], i[1])
                        else:
                            metric(i[0], i[1], stk)  # if balance is staked
                    c += 1
                    if c > 5:
                        c = 0
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
