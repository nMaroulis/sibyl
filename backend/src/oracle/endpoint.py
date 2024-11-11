from fastapi import APIRouter
from backend.src.oracle.oracle import Oracle

# APIRouter creates path operations for user module
router = APIRouter(
    prefix="/oracle",
    tags=["Oracle"],
    responses={404: {"description": "Not found"}},
)


@router.get("/forecast/btc")
def get_btc_forecast(interval: str):
    try:
        client = Oracle()
        pred = client.generate_btc_prediction()
        return {"status": "success", "data": list(pred)}
    except Exception as e:
        print(f"Oracle :: forecast/btc :: {e}")
        return {"status": "error", "data": []}
