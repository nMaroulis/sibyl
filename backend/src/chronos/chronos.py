import pandas as pd
# from tensorflow.keras.models import load_model
import yfinance as yf
from pickle import load
from datetime import datetime, timedelta
from numpy import zeros
import os

MODEL_PATH = f"backend/src/chronos/models/chronos_v0.1.keras"
SCALER_PATH = f"backend/src/chronos/preprocessing/minmax_scaler-7f.pkl"


class Chronos:
    def __init__(self):
        self.lookback = 60  # days
        self.forecast_horizon = 7  # days
        self.model = None # load_model(MODEL_PATH)
        self.scaler = load(open(SCALER_PATH, 'rb'))
        self.dataset = pd.DataFrame()
        self.model_input = None
        self.current_btc_price = None

    def fetch_dataset(self):
        start_date = (datetime.today() - timedelta(days=self.lookback)).strftime('%Y-%m-%d')
        end_date = datetime.today().strftime('%Y-%m-%d')
        bitcoin = yf.download('BTC-USD', start=start_date, end=end_date)
        self.dataset['bitcoin_price'] = bitcoin['Close']  # Adj Close
        self.current_btc_price = self.dataset['bitcoin_price'].values
        sp500 = yf.download('^GSPC', start=start_date, end=end_date)
        self.dataset['sp500_price'] = sp500['Close']
        gold = yf.download('GC=F', start=start_date, end=end_date)
        self.dataset['gold_price'] = gold['Close']
        usd_index = yf.download('DX-Y.NYB', start=start_date, end=end_date)
        self.dataset['usd_index'] = usd_index['Close']
        vol_index = yf.download('^VIX', start=start_date, end=end_date)
        self.dataset['volatility_index'] = vol_index['Close']
        irx = yf.download('^IRX', start=start_date, end=end_date)
        self.dataset['interest_rate'] = irx['Close']
        oil = yf.download('CL=F', start=start_date, end=end_date)
        self.dataset['oil_price'] = oil['Close']

        self.dataset.ffill(inplace=True)
        self.dataset.dropna(inplace=True)

    def dataset_preprocessing(self):
        self.dataset = self.scaler.transform(
            self.dataset[['bitcoin_price', 'sp500_price', 'gold_price', 'usd_index', 'oil_price',
                          'volatility_index', 'interest_rate']])

    def create_model_input(self):
        self.model_input = self.dataset.reshape(1, self.dataset.shape[0], self.dataset.shape[1])  # TODO - examine here: reshape(1, self.lookback, self.dataset.shape[1])

    def generate_model_prediction(self):
        y_pred = self.model.predict(self.model_input)
        dummy_2d_array = zeros((7, 7))
        dummy_2d_array[:, 0] = y_pred[0]
        rescaled_2d_array = self.scaler.inverse_transform(dummy_2d_array)
        return rescaled_2d_array[:, 0]

    def generate_output(self, y_pred):
        prices = list(self.current_btc_price) + list(y_pred)
        result = []
        time_diff = len(self.current_btc_price)
        for i, price in enumerate(prices):
            result.append({"date": (datetime.today() - timedelta(days=time_diff)).strftime('%Y-%m-%d'), "price": price})
            time_diff -= 1
        return result

    def generate_btc_prediction(self):
        # self.fetch_dataset()
        # self.dataset_preprocessing()
        # self.create_model_input()
        # y_pred = self.generate_model_prediction()
        return [] # self.generate_output(y_pred)
