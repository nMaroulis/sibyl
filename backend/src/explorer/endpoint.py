from fastapi import APIRouter
from backend.src.explorer.explorer import Explorer
import json


# APIRouter creates path operations for user module
router = APIRouter(
    prefix="/explorer",
    tags=["Explorer"],
    responses={404: {"description": "Not found"}},
)


@router.get("/blockchain/blocks")
def get_bitcoin_(blockchain: str, block_count: int):
    explorer = Explorer(blockchain)
    res = explorer.get_blocks(block_count)
    if res is None:
        return {"status": "error", "data": []}
    else:
        return {"status": "success", "data": res}
