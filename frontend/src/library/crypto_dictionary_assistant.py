from pandas import DataFrame


def get_crypto_coin_dict():
    crypto_coin_dict = {
        'Binance Coin [BNB]': 'BNB',
        'Bitcoin [BTC]': 'BTC',
        'Cardano [ADA]': 'ADA',
        'Chainlink [LINK]': 'LINK',
        'Dogecoin [DOGE]': 'DOGE',
        'Ethereum [ETH]': 'ETH',
        'Litecoin [LTC]': 'LTC',
        'Mask Network [MASK]': 'MASK',
        'Polkadot [DOT]': 'DOT',
        'Polygon [MATIC]': 'MATIC',
        'Solana [SOL]': 'SOL',
        'Stellar [XLM]': 'XLM',
        'TRON [TRX]': 'TRX',
        'VeChain [VET]': 'VET',
        'XRP [XRP]': 'XRP',
    }
    return crypto_coin_dict


def get_crypto_coin_dict_inv():
    crypto_coin_dict = {
        'BNB': 'Binance Coin [BNB]',
        'BTC': 'Bitcoin [BTC]',
        'ADA': 'Cardano [ADA]',
        'LINK': 'Chainlink [LINK]',
        'DOGE': 'Dogecoin [DOGE]',
        'ETH': 'Ethereum [ETH]',
        'LTC': 'Litecoin [LTC]',
        'MASK': 'Mask Network [MASK]',
        'DOT': 'Polkadot [DOT]',
        'MATIC': 'Polygon [MATIC]',
        'SOL': 'Solana [SOL]',
        'XLM': 'Stellar [XLM]',
        'TRX': 'TRON [TRX]',
        'VET': 'VeChain [VET]',
        'XRP': 'XRP [XRP]',
    }
    return crypto_coin_dict


def get_crypto_coin_listing_name(crypto_name='Bitcoin [BTC]'):
    return get_crypto_coin_dict().get(crypto_name)