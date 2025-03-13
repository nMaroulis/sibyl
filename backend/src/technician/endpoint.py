from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.src.technician.technician import Technician
from typing import Optional


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
        print(res)
    except Exception as e:
        print(f"TECHNICIAN :: status/api/all :: {e}")
        res = {}
    return res


class APIParams(BaseModel):
    api_name: str
    api_key: str
    secret_key: Optional[str] = None
    api_metadata: Optional[str] = None

@router.post("/credentials/apis/new")
def insert_update_api_keys(api_params: APIParams):
    try:
        # check if exists (insert or update)
        res = technician_worker.insert_api_key_to_db(api_params.api_name, api_params.api_key, api_params.secret_key, api_params.api_metadata)
        if res:
            return {'status': 'success'}
        else:
            raise HTTPException(status_code=400, detail="Failed to insert API key.")
    except Exception as e:
        print(f"TECHNICIAN :: credentials/apis/exchange :: {e}")
        raise HTTPException(status_code=400, detail="Failed to insert API key.")