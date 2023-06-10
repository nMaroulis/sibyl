from fastapi import APIRouter
from fastapi import Query
from typing import Optional, List
import json


# APIRouter creates path operations for user module
router = APIRouter(
    prefix="/broker",
    tags=["Broker"],
    responses={404: {"description": "Not found"}},
)


@router.get("/trade/orders/active")
def get_active_trade_orders():
    res = {}
    json_data = json.dumps(res)
    return json_data

