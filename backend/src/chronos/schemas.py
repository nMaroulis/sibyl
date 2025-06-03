from pydantic import BaseModel
from typing import List, Optional
from datetime import date


class PricePrediction(BaseModel):
    date: date
    price: float

class PricePredictionResponse(BaseModel):
    status: str
    data: List[PricePrediction]

class PricePredictionRequest(BaseModel):
    coin: str
    interval: str
    forecast_window: Optional[int]