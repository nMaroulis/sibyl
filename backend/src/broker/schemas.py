from pydantic import BaseModel
from typing import Optional, Dict, Any


class SpotTradeRequest(BaseModel):
    exchange: str
    order_type: str
    quote_asset: str
    base_asset: str
    side: str
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    time_in_force: Optional[str] = None


class SpotTradeResponse(BaseModel):
    status: str
    message: str



class StrategyRequest(BaseModel):
    exchange: str
    quote_asset: str
    quote_amount: float
    base_asset: str
    time_interval: str
    strategy: str
    num_trades: int
    dataset_size: int
    params: Dict[str, Any]  # Holds strategy-specific parameters
