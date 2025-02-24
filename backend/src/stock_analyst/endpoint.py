from fastapi import APIRouter, HTTPException
from backend.src.stock_analyst.yf_client import get_stock_details
from backend.src.stock_analyst.portfolio_archive import fetch_senate_trades
from backend.src.llm_hub.llm_client_factory import LLMClientFactory


# APIRouter creates path operations for user module
router = APIRouter(
    prefix="/stock_analyst",
    tags=["Stock Analyst"],
    responses={404: {"description": "Not found"}},
)


@router.get("/yf/stock_details")
def get_stock_info(stock_symbol: str):
    try:
        stock_details = get_stock_details(stock_symbol)
        return {"status": "success", "data": stock_details}
    except Exception as e:
        raise HTTPException(status_code=404, detail="HF client failed")


@router.get("/advisor/llm")
def get_llm_advice(stock_symbol: str, llm_api: str):
    try:
        # load LLM API client
        llm_api_client = LLMClientFactory.get_client(llm_api)

        # fetch stock data
        stock_json = get_stock_info(stock_symbol)
        stock_text =  f""" 52 Week High: ${stock_json.get('fiftyTwoWeekHigh', 'N/A')}, 52 Week Low: ${stock_json.get('fiftyTwoWeekLow', 'N/A')}, Target Mean Price: ${stock_json.get('targetMeanPrice', 'N/A')}, Yahoo Finance Analyst Opinions: {stock_json.get('numberOfAnalystOpinions', 'N/A')} Analysts generated the following recommendation {stock_json.get('recommendationKey', 'N/A')} with a score of {stock_json.get('recommendationMean', 'N/A')}."""

        prompt = f"""
            You are a financial expert. Analyze the following stock information and determine if it's a good investment for short-term and long-term.
            Stock Data:
            {stock_text} 
            Provide an evaluation, reasoning, and a confidence score (0 to 100).
            """
        # generate response
        res = llm_api_client.generate_response(prompt, 250, 0.7)

        return {"status": "success", "data": res}
    except Exception as e:
        print(e)
        raise HTTPException(status_code=404, detail="LLM API failed")


@router.get("/portfolio/senates")
def get_senate_portfolios():
    try:
        senate_portfolio = fetch_senate_trades()
        return {"status": "success", "data": senate_portfolio}
    except Exception as e:
        print(e)
        raise HTTPException(status_code=404, detail="Senate portfolio API failed")