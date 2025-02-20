from fastapi import APIRouter, HTTPException
from backend.src.stock_analyst.yf_client import get_stock_details
from backend.src.stock_analyst.portfolio_archive import fetch_senate_trades

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


@router.get("/portfolio/senates")
def get_senate_portfolios():
    try:
        senate_portfolio = fetch_senate_trades()
        return {"status": "success", "data": senate_portfolio}
    except Exception as e:
        print(e)
        raise HTTPException(status_code=404, detail="Senate portfolio API failed")