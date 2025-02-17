import yfinance as yf
from typing import Any
from numpy import isnan


def replace_nan(data: Any) -> Any:
    """
    Recursive function to replace NaN with None in nested data
    """
    if isinstance(data, dict):
        return {key: replace_nan(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [replace_nan(item) for item in data]
    elif isinstance(data, float) and isnan(data):
        return None
    else:
        return data


def get_stock_details(stock_symbol: str) -> dict:
    """
    Fetches all possible details about a stock from Yahoo Finance.

    Args:
        stock_symbol (str): The symbol of the stock to fetch details for.

    Returns:
        dict: A dictionary containing various details about the stock.
    """
    # Fetch the stock data
    stock = yf.Ticker(stock_symbol)

    # Prepare the details dictionary
    details = {
        "symbol": stock_symbol,
        "info": stock.info if stock.info is not None else {},  # General company info
        # "historical_data": stock.history(period="1y").to_dict() if stock.history(period="1y") is not None else {},
        # Historical data
        "financials": stock.financials.to_dict() if stock.financials is not None else {},  # Financials
        "quarterly_financials": stock.quarterly_financials.to_dict() if stock.quarterly_financials is not None else {},
        # Quarterly financials
        "earnings": stock.earnings.to_dict() if stock.earnings is not None else {},  # Annual earnings
        "quarterly_earnings": stock.quarterly_earnings.to_dict() if stock.quarterly_earnings is not None else {},
        # Quarterly earnings
        "recommendations": stock.recommendations.to_dict() if stock.recommendations is not None else {},
        # Analyst recommendations
        "sustainability": stock.sustainability.to_dict() if stock.sustainability is not None else {},  # ESG scores
        "major_holders": stock.major_holders.to_dict() if stock.major_holders is not None else {},  # Major holders
        "institutional_holders": stock.institutional_holders.to_dict() if stock.institutional_holders is not None else {},
        # Institutional holders
        "dividends": stock.dividends.to_list() if stock.dividends is not None else [],  # Dividends history
        "splits": stock.splits.to_list() if stock.splits is not None else [],  # Stock splits history
        "options": stock.options if stock.options is not None else [],  # Available option expirations
    }

    details = replace_nan(details)

    return details
