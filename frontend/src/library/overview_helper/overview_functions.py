import requests
from streamlit import sidebar, write, metric, columns


def check_connection():
    url = f"http://127.0.0.1:8000/"
    response = requests.get(url)
    if response.status_code == 200:
        sidebar.success('📶 Server Connection Active')
    else:
        sidebar.error('📶 Server Connection Failed')
    return 0


def get_wallet_balances():
    url = "http://127.0.0.1:8000/account/spot/overview"
    response = requests.get(url)
    data = response.json()
    wallet_list = []
    for coin in data.get('spot_balances'):
        wallet_list.append([coin, round(data.get('spot_balances').get(coin).get('free'), 4)])  # can add round(data.get('spot_balances').get(coin).get('locked')

    write('SPOT')
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
    return 0

