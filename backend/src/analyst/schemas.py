from pydantic import BaseModel, Field
from typing import List, Dict, Optional


# ========== /symbol/klines/analysis ==========
class KlineAnalytics(BaseModel):
    open_time: float
    open_price: float
    high: float
    low: float
    close_price: float
    close_time: float
    volume: float
    trades_num: float
    Moving_Average: float
    RSI: float
    LowerBand: float
    UpperBand: float


class SymbolAnalysisResponse(BaseModel):
    klines: Dict[str, KlineAnalytics]
    score: float = Field(..., ge=0, le=100)


# ========== /asset/klines ==========
class Kline(BaseModel):
    open_time: float
    open_price: float
    high: float
    low: float
    close_price: float
    close_time: float
    volume: float
    trades_num: float


# ========== /account/spot/balance ==========
class SpotBalance(BaseModel):
    free: float
    locked: float
    price: float


class SpotBalancesResponse(BaseModel):
    spot_balances: Dict[str, SpotBalance]


# ========== /available_coins/symbol_name_map/update ==========
class UpdateResponse(BaseModel):
    Success: Optional[str] = None
    Error: Optional[str] = None
