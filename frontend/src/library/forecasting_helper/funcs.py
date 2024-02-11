
def calc_rsi(s, window=14):
    delta = s.astype(float).diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    RS = gain / loss
    return 100 - (100 / (1 + RS))


def calc_ema(method="exponential", s=None, window=5):
    if method == "exponential":
        return s.ewm(span=window, adjust=False).mean()
    else:
        return s.rolling(window=window).mean()


def calc_bollinger_bands(ma, price, window=3):
    std = 2
    lower_band = ma - std * price.ewm(span=window).std()
    upper_band = ma + std * price.ewm(span=window).std()
    return lower_band, upper_band