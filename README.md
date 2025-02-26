
<div align="center">

[//]: # (  <img src="https://repository-images.githubusercontent.com/648387594/566640d6-e1c4-426d-b2f2-bed885d07e97">)
  <img src="https://repository-images.githubusercontent.com/648387594/3557377e-1c09-45a9-a759-b0d27cf3c501">
</div>

[![Python](https://img.shields.io/badge/python-v3.12-yellow)]()
[![Streamlit](https://img.shields.io/badge/streamlit-v1.42-red)]()
[![FastAPI](https://img.shields.io/badge/fastapi-v0.115.8-blue)]()
[![Tensorflow](https://img.shields.io/badge/tensorflow-v2.18.0-orange)]()
[![Statsmodels](https://img.shields.io/badge/statsmodels-v0.14-pink)]()
[![Pandas](https://img.shields.io/badge/pandas-v2.2.3-lightgrey)]()
[![Plotly](https://img.shields.io/badge/plotly-v6.0.0-green)]()
[![Sklearn](https://img.shields.io/badge/Scikit_Learn-v1.6.1-purple)]()


# Sibyl - Your AI-Powered Crypto Trading Hub with a UI

[//]: # (<hr>)

[//]: # (<span style="color: red; font-size: 16px;">pre-alpha version</span>)

[//]: # (<br>)

Welcome to **Sibyl**! This application is your centralized hub for all things crypto. With Sibyl, you can connect multiple crypto exchange accounts, deploy smart trading strategies, and access a wide range of AI-powered tools—all within a secure, locally deployed environment.

## Key Features

### Interactive Dashboard UI
The intuitive dashboard provides a comprehensive view of your crypto activities. Manage your trading strategies, analyze market trends, and keep an eye on the latest news—all in one place.


### AI-Driven Smart Trading Strategies - Oracle Module 🔮
Sibyl allows you to deploy intelligent trading strategies using advanced AI models. Leverage custom TensorFlow Bi-Directional LSTMs, Gated Transformer Units (GTUs), and ARIMA models to make informed trading decisions. With these advanced models, you can optimize your trading for maximum returns.


### Data Analysis & Visualization - Analyst Module 📈

Track your profits and losses with detailed tables and plots, allowing you to measure the success of each trading order.

Sibyl offers powerful data analysis and visualization tools to support your trading decisions:

- Correlation Analysis
- SHAP Feature Importance
- Regression Analysis

Visualize the data with custom plots and tables for clear insights.

### NLP Models - Reporter Module 🕵🏻‍
Stay informed with the Natural Language Processing (NLP) tools:

- Web scraping for the latest crypto news
- Text summarization for quick news highlights
- Sentiment analysis using advanced language models to gauge market mood

### Customized Strategy Planning - Broker Module 🎯
Develop and deploy your own trading strategies, including:

- Parametrized trading based on AI-driven models
- Scalping (Greedy), Dollar-Cost Averaging (DCA), Arbitrage and more...


### Connect with Popular Exchanges - Technician Module 🛠️
Sibyl supports API connections with major crypto exchanges. Currently supported:

- Binance.com
- Binance Testnet

Additional exchanges are planned for future releases.
- Coinbase
- Uniswap
- Kraken

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


## Roadmap
The development roadmap includes exciting new features:

- A Reinforcement Learning Agent that automatically places buy/sell orders based on optimized strategies and timing.

---

If you have any questions or suggestions, please open an issue or submit a pull request. I'm excited to see how you use Sibyl to enhance your crypto trading experience!

