from frontend.src.utils.settings_helper.html_elements import status_card, status_card_style, compact_card_style, compact_card, compact_card_header
from streamlit import html, session_state
from frontend.src.utils.settings_helper.client import fetch_apis_status

"""
Four states of Status
    Active: The API credentials are stored at the backend Server and connection works OK
    Unavailable: The API is not yet implemented
    Available: The API is available in the backend, but credentials have not yet been filled
    *Invalid Keys: API Keys have been given but don't work
"""


CRYPTO_APIS = {
    "binance": ("Binance API", "https://www.logo.wine/a/logo/Binance/Binance-Vertical2-Dark-Background-Logo.wine.svg"),
    "binance_testnet": ("Binance Testnet API", "https://www.logo.wine/a/logo/Binance/Binance-Vertical2-Dark-Background-Logo.wine.svg"),
    "kraken": ("Kraken API", "https://media.licdn.com/dms/image/D4E0BAQFm8yg0gGJN1A/company-logo_200_200/0/1697458897774/krakenfx_logo?e=2147483647&v=beta&t=CTWrqJakEEIx4lAPmddjLjt7e4Xi0HQqDTi7k9p3RPM"),
    "coinbase": ("Coinbase API", "https://alternative.me/media/256/coinbase-icon-kdtz42w4efva6qiu-c.png"),
    "coinbase_sandbox": ("Coinbase Sandbox API", "https://back.gainium.io/uploads/Coinbase_Pro_d32bc1e094.jpeg"),
    "mock_exchange": ("Mock Exchange API", "https://cdn-icons-png.flaticon.com/512/994/994152.png")
}

LLM_APIS = {
    "openai": ("OpenAI API", "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSFJYCiV_aHxCRPoVcLeOChZWnb_qVxSQMm4Jr-C_x_0A&s"),
    "gemini": ("Gemini API", "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQV1QWx0soc08N7wU8LjH95wZTkF_q13tg1KH4AOTs3xw&s"),
    "hugging_face": ("Hugging Face API", "https://cdn.worldvectorlogo.com/logos/huggingface-2.svg"),
    "anthropic": ("Anthropic", "https://www.appengine.ai/uploads/images/profile/logo/Anthropic-AI.png")
}

LOCAL_LLMS = {
    "llama_cpp": ("Local LLAMA CPP", "https://repository-images.githubusercontent.com/612354784/c59e3320-a236-4182-941f-ea3f1a0f50e7"),
    "tgi": ("Local TGI", "https://cdn-avatars.huggingface.co/v1/production/uploads/5f17f0a0925b9863e28ad517/NXI_YNqaf9ZvhVczj0kpz.png")
}

PRICE_API = {
    "coinmarketcap": ("CoinMarketCap API", "data:image/jpeg;base64,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")
}


def show_status_cards(only_exchange: bool = False) -> None:
    status_json = fetch_apis_status("all")
    status_list = list(status_json.values())
    # EXCHANGE APIS
    global CRYPTO_APIS
    status_card_style()

    html_txt = """<div class="section" id="apis">"""

    i = 0
    for k, v in CRYPTO_APIS.items():


        html_txt += status_card(v[0], v[1], status_json[k])
        i += 1

    # LLM APIS
    # status_card_header("LLM APIs")
    for k, v in LLM_APIS.items():
        html_txt += status_card(v[0], v[1], status_json[k])
        i += 1


    # Local LLMs
    for k, v in LOCAL_LLMS.items():
        html_txt += status_card(v[0], v[1], status_json[k])
        i += 1

    # Price History APIS
    # status_card_header("LLM APIs")
    for k, v in PRICE_API.items():
        html_txt += status_card(v[0], v[1], status_json[k])
        i += 1
    html_txt += """</div>"""
    html(html_txt)


def show_homepage_status_cards() -> None:
    global CRYPTO_APIS
    status_card_style()
    statuses = [session_state['backend_status'], session_state["binance_api_status"], session_state["binance_testnet_api_status"],
                session_state["kraken_api_status"], session_state["coinbase_api_status"], session_state["coinbase_sandbox_api_status"], session_state["mock_exchange_api_status"]]
    i = 1
    html_txt = """<div class="section" id="apis">"""
    html_txt += status_card('Backend Server', "https://mdevelopers.com/storage/backend1_a9b6dc2f.png", statuses[0])
    for k, v in CRYPTO_APIS.items():
        html_txt += status_card(v[0], v[1], statuses[i])
        i += 1
    html_txt += """</div>"""
    html(html_txt)


def exchange_api_status_check() -> None:
    if "api_status_check" not in session_state:
        status_dict = fetch_apis_status("exchanges")

        exchanges = ["Binance", "Binance Testnet", "Kraken", "Coinbase", "Coinbase Sandbox", "Mock Exchange"]

        # A list that contains the Names of the Active Exchanges that can be used by each component
        session_state["available_exchange_apis"] = []

        for exchange in exchanges:
            exchange_name = exchange.lower().replace(" ", "_")
            status = status_dict[exchange_name]
            session_state[f"{exchange_name}_api_status"] = status
            if status == "Active":
                session_state["available_exchange_apis"].append(exchange)


def show_homepage_status_cards_alt() -> None:

    html_txt = """
    <style>
    .article-card {
      width: 120px;
      height: 80px;
      border-radius: 12px;
      overflow: hidden;
      position: relative;
      font-family: Arial, Helvetica, sans-serif;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12), 0 1px 2px rgba(0, 0, 0, 0.24);
      transition: all 300ms;
      display:inline-block;
    }
    
    .article-card:hover {
      transform: translateY(-2px);
      box-shadow: 0 14px 28px rgba(0, 0, 0, 0.25), 0 10px 10px rgba(0, 0, 0, 0.22);
    }
    
    .article-card img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
    
    .article-card .content {
      box-sizing: border-box;
      width: 100%;
      position: absolute;
      padding: 5px 5px 5px 5px;
      height: auto;
      top: 0;
      background: linear-gradient(rgba(0, 0, 0, 0.8), transparent);
    }
    
    .article-card .date,
    .article-card .title {
      margin: 0;
    }
    
    .article-card .date {
      font-size: 10px;
      color: rgba(255, 255, 255, 0.9);
      margin-bottom: 1px;
    }
    
    .article-card .title {
      font-size: 12px;
      color: #fff;
    }
    </style>
    """
    global CRYPTO_APIS
    statuses = [session_state['backend_status'], session_state["binance_api_status"], session_state["binance_testnet_api_status"],
                session_state["kraken_api_status"], session_state["coinbase_api_status"], session_state["coinbase_sandbox_api_status"], session_state["mock_exchange_api_status"]]

    i = 1
    html_txt += """<div class="section" id="apis">"""

    for k, v in CRYPTO_APIS.items():
        html_txt += f"""
      <div class="article-card">
        <div class="content">
          <p class="title">{k}</p>
         <p class="date">{statuses[i]}</p>
        </div>
        <img src="{v}" alt="article-cover" />
      </div>
        """
        i += 1
    html_txt += """</div>"""
    html(html_txt)
