from fastapi import APIRouter
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
