from fastapi import APIRouter
from backend.src.chronos.chronos import Chronos

# APIRouter creates path operations for user module
router = APIRouter(
    prefix="/chronos",
    tags=["Chronos"],
    responses={404: {"description": "Not found"}},
)


@router.get("/forecast/btc")
def get_btc_forecast(interval: str):
    try:
        client = Chronos()
        pred = client.generate_btc_prediction()
        return {"status": "success", "data": list(pred)}
    except Exception as e:
        print(f"Chronos :: forecast/btc :: {e}")
        return {"status": "error", "data": []}
