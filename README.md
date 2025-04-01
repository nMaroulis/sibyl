
<div align="center">

[//]: # (  <img src="https://repository-images.githubusercontent.com/648387594/566640d6-e1c4-426d-b2f2-bed885d07e97">)
  <img src="https://repository-images.githubusercontent.com/648387594/3557377e-1c09-45a9-a759-b0d27cf3c501">
</div>

[![Python](https://img.shields.io/badge/python-v3.12-yellow)]()
[![Streamlit](https://img.shields.io/badge/streamlit-v1.44-red)]()
[![FastAPI](https://img.shields.io/badge/fastapi-v0.115.8-blue)]()
[![Tensorflow](https://img.shields.io/badge/tensorflow-v2.18.0-orange)]()
[![Statsmodels](https://img.shields.io/badge/statsmodels-v0.14-pink)]()
[![Pandas](https://img.shields.io/badge/pandas-v2.2.3-lightgrey)]()
[![Plotly](https://img.shields.io/badge/plotly-v6.0.1-green)]()
[![Sklearn](https://img.shields.io/badge/Scikit_Learn-v1.6.1-purple)]()


# Sibyl - Your AI-Powered Crypto Trading Hub with a UI

[//]: # (<hr>)

[//]: # (<span style="color: red; font-size: 16px;">pre-alpha version</span>)

[//]: # (<br>)

Welcome to **Sibyl**! This application is your centralized hub for all things crypto. With Sibyl, you can connect multiple crypto exchange accounts, deploy smart trading strategies, and access a wide range of AI-powered tools—all within a secure, locally deployed environment.

## Key Features

### Interactive Dashboard UI
The intuitive dashboard provides a comprehensive view of your crypto activities. Manage your trading strategies, analyze market trends, and keep an eye on the latest news—all in one place.


### Strategy Planning - Broker Module 🎯
Tune and deploy trading strategies and monitor their performance through a real-time UI:

- Currently supported trading algorithm:
  - Generic strategy algorithms: Bollinger Bands, RSI and EMA crossover
  - Sibyl advanced custom strategy algorithms: **Bollinger Surge**, **Impulse Breakout** and **Quantum Momentum**.
- Customize the parameters for each algorithm and choose the desired market you want to deploy it.
- **Backtesting** for each strategy before it is deployed. Get strategy performance metrics and plots on historic data.
- ```Strategy Console```: Monitor in real-time the performance of the algorithm
  - Logs Table
  - Evaluation metrics (profit ratio, sharpe ratio, drawdown, sortino and more..)
  - Real-time Line plot where the actions of the algorithm are shown.

Modules:
- Strategies: All the classes that implement a strategy logic. Inherit the ```BaseStrategy``` class
- ```Tactician```: Takes a Strategy as input and is responsible for running it. It is run in a loop, where the interval is based on the strategy interval. Uses the ```TacticianExchangeInterface``` to communicate with the Exchange API clients.
- ```Evaluator```: Takes as inputs the strategy logs and calculates the Evaluation metrics.
- ```Backtester```: Aggregates historical data and evaluates the strategies on them.

TBA: AI-based strategy algorithm, LLM Assistant on Strategy planning.


### SPOT Trading - Broker Module 💰
Create and place a SPOT order through the sibyl UI. This order will be first sent as a test order, and if it is validated it will be placed on your Exchange API.
The Spot order is then saved in the TradingHistory DB, to retrieve its status and get analytics.


### Price Movement Prediction using ML - Oracle Module 🔮
Leverage custom TensorFlow Bi-Directional LSTMs, Gated Transformer Units (GTUs), and ARIMA models to forecast and asset's price and make informed trading decisions. 
- Oracle tab in the UI: choose an asset and call the Oracle to get the price prediction.

TBA: AI-powered strategies that utilize the Oracle models.


### Data Analysis & Visualization - Analyst Module 📈


Sibyl offers powerful data analysis and visualization tools to support your trading decisions:

- Line and Candle Plots with statistics (Bollinger Bands, RSI, EMA and more..)
- Correlation Analysis
- SHAP Feature Importance
- Regression Analysis

Visualize the data with custom plots and tables for clear insights.

Track your profits and losses with detailed tables and plots, allowing you to measure the success of each trading order.


### NLP Models - Reporter Module 🕵🏻‍
Stay informed with the Natural Language Processing (NLP) tools:

- Web scraping for the latest crypto news
- Text summarization for quick news highlights
- Sentiment analysis using advanced language models to gauge market mood
- LLM-powered chatbot, to ask questions about the latest crypto news.


### Connect with Popular Exchanges - Technician Module 🛠️
Sibyl supports API connections with major crypto exchanges. Currently supported:

- Binance.com
- Binance Testnet
- Coinbase Sandbox

Additional exchanges are planned for future releases.
- Coinbase
- Bybit
- Kraken


### Crypto Wiki Chatbot - Wiki Module 💬
An interactive **chatbot** which is based on a custom **RAG system**, which includes thousands of crypto-related publications, books and articles.
After you ask a crypto-related question, the embeddings for your query are created and the most similar embeddings are found in the ***chromaDB*** Embeddings Database.
The similarity method is a hybrid approach, using cosine similarity, BM25 keyword search matching and FAISS indexing similarity.

In order to use this functionality, you have to:
1. Provide a valid HuggingFace or OpenAI API key, to be stored in the local encrypted Database.
2. Download the chromaDB Embeddings Database, which is not by default provided in the implementation. The download is available through the UI, or adding manually the following file https://drive.google.com/file/d/15Vrxs6sbPnlZZURGr5DopZHlcwEtvaou/view?usp=share_link in the *database/wiki_rag* directory.


### Evaluate Stock - Stock Analysis Module 📊
Choose a Company from a list of available company stocks and:

- Get Company's Information
- Analysis if a stock is worth buying or not based on various indicators
- Get insights about U.S. senators' stock portfolios
- Future Release: Rating based on custom ML model


## Security & Local Deployment
Sibyl is designed for local deployment, ensuring your data stays secure. You have complete control over your trading activities and account connections. No sensitive information is stored on external servers, giving you peace of mind.
### Local Databases
#### API Key Storage 
> All **API keys** are stored ***locally*** on an **encrypted** SQlite Database, with a **unique encryption key** generated on your local file system. This Database uses SQLAlchemy for ORM. You may find the database and the encryption key at */database*

> All **trades** made through Sibyl strategies are stored in a local SQlite DB without keeping any personal information.

## Architecture

<div align="center">

[//]: # (  <img src="https://raw.githubusercontent.com/nMaroulis/sibyl/refs/heads/main/assets/architecture.png">)
  <img src="https://raw.githubusercontent.com/nMaroulis/sibyl/refs/heads/main/assets/architecture.png">
</div>


## Deployment

**1. Virtual Environment - Recommended for Apple silicon and ARM systems, so Pypi takes care of arm64 libraries.**

Install Python 3.12 on your system:

```sh
# macOS
$ brew install python@3.12 
# Linux (apt)
$ sudo apt install python==3.12

$ cd sibyl

$ python3.12 -m venv sibyl
$ source sibyl/bin/activate
$ pip install -r requirements.txt # poetry config file is also available

$ python3.12 main.py
```

**2. Dockerfile - Recommended for x86 systems.**

```sh
$ docker build -t sibyl_image .
$ docker run -p 8501:8501 -p 8000:8000 -p 50051:50051 sibyl_image
```

Access the frontend from your browser at ```http://localhost:8501```


## Roadmap
The development roadmap includes exciting new features:

- A Reinforcement Learning Agent that automatically places buy/sell orders based on optimized strategies and timing.

---

If you have any questions or suggestions, please open an issue or submit a pull request. I'm excited to see how you use Sibyl to enhance your crypto trading experience!

