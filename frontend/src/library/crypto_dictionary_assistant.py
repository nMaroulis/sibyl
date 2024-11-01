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


def get_crypto_coin_listing_name(crypto_name: str = 'Bitcoin [BTC]'):
    return get_crypto_coin_dict().get(crypto_name)


def get_crypto_name_regex(crypto_name: str = 'Bitcoin [BTC]'):
    if '[' in crypto_name and ']' in crypto_name:
        coin_name = ''.join(crypto_name.split('[')[1].split(']')[0])
        return coin_name
    else:
        return crypto_name
