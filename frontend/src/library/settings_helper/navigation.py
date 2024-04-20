from frontend.src.library.settings_helper.html_elements import status_card, status_card_style, status_card_header
from streamlit import columns, html

"""
Four states of Status
    Active: The API credentials are stored at the backend Server and connection works OK
    Unavailable: The API is not yet implemented
    Available: The API is available in the backend, but credentials have not yet been filled
    *Invalid Keys: API Keys have been given but don't work
"""
CRYPTO_APIS = {'Binance API': "https://www.logo.wine/a/logo/Binance/Binance-Vertical2-Dark-Background-Logo.wine.svg",
                'Binance Testnet API': "https://www.logo.wine/a/logo/Binance/Binance-Vertical2-Dark-Background-Logo.wine.svg",
                'Kraken API': "https://media.licdn.com/dms/image/D4E0BAQFm8yg0gGJN1A/company-logo_200_200/0/1697458897774/krakenfx_logo?e=2147483647&v=beta&t=CTWrqJakEEIx4lAPmddjLjt7e4Xi0HQqDTi7k9p3RPM",
                'Coinbase API': "https://alternative.me/media/256/coinbase-icon-kdtz42w4efva6qiu-c.png"}

LLM_APIS = {'OpenAI API': "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSFJYCiV_aHxCRPoVcLeOChZWnb_qVxSQMm4Jr-C_x_0A&s",
                'Gemini API': "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQV1QWx0soc08N7wU8LjH95wZTkF_q13tg1KH4AOTs3xw&s",
                'Kraken API': "https://huggingface.co/dfurman/Falcon-7B-Chat-v0.1/resolve/main/falcon.webp"
            }



def show_status_cards():
    # EXCHANGE APIS
    global CRYPTO_APIS
    status_card_style()
    # status_card_header("Exchange APIs")
    api_cols = columns(4)
    i = 0
    statuses = ['Active', 'Active', 'Unavailable', 'Unavailable']
    for k, v in CRYPTO_APIS.items():
        with api_cols[i]:
            status_card(k, v, statuses[i])
        i += 1

    # LLM APIS
    i = 0
    # status_card_header("LLM APIs")
    statuses = ['Unavailable', 'Unavailable', 'Unavailable']
    for k, v in LLM_APIS.items():
        with api_cols[i]:
            status_card(k, v, statuses[i])
        i += 1


    return
