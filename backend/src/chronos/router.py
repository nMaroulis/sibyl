from fastapi import APIRouter, HTTPException, Query
from backend.src.chronos.chronos import Chronos
from backend.src.chronos.schemas import PricePredictionResponse

# APIRouter creates path operations for user module
router = APIRouter(
    prefix="/chronos",
    tags=["Chronos"],
    responses={404: {"description": "Not found"}},
)


@router.get("/forecast/crypto/price", response_model=PricePredictionResponse)
def get_btc_forecast(asset: str = Query(description="Asset symbol like BTC or ETH"), interval: str = Query(), forecast_window: int = None) -> PricePredictionResponse:
    try:
        client = Chronos()
        pred = client.generate_btc_prediction()
        res = {"status": "success", "data": list(pred)}
        return res
    except Exception as e:
        print(f"Chronos :: forecast :: {e}")
        raise HTTPException(status_code=500, detail=str(e))
