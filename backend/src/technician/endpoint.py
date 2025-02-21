from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.src.technician.technician import Technician

# APIRouter creates path operations for user module
router = APIRouter(
    prefix="/technician",
    tags=["Technician"],
    responses={404: {"description": "Not found"}},
)

technician_worker = Technician()


@router.get("/status/api/{api_name}")
def get_api_status(api_name: str = 'binance'):
    try:
        res = technician_worker.api_status_check(api_name)
    except Exception as e:
        print(f"TECHNICIAN :: status/api/all :: {e}")
        res = {}
    return res


class ExchangeAPIParams(BaseModel):
    exchange_name: str
    api_key: str
    secret_key: str

@router.post("/credentials/apis/exchange")
def insert_update_exchange_api_keys(exchange_api_params: ExchangeAPIParams):
    try:
        # check if exists (insert or update)
        res = technician_worker.insert_api_key_to_db(exchange_api_params.exchange_name, exchange_api_params.api_key, exchange_api_params.secret_key)
        return {'status': 'success'}
    except Exception as e:
        print(f"TECHNICIAN :: credentials/apis/exchange :: {e}")
        raise HTTPException(status_code=400, detail="Failed to insert API key.")