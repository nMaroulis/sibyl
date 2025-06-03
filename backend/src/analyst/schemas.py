from typing import List, Optional, Dict
from pydantic import BaseModel, Field, validator, RootModel
import math


class Kline(BaseModel):
    open_time: int = Field(..., description="Opening time as a Unix timestamp in milliseconds")
    open_price: float = Field(..., description="Opening price")
    high: float = Field(..., description="Highest price in the interval")
    low: float = Field(..., description="Lowest price in the interval")
    close_price: float = Field(..., description="Closing price")
    close_time: float = Field(..., description="Closing time as Unix timestamp in milliseconds (float in example)")
    volume: float = Field(..., description="Trading volume during the interval")
    trades_num: float = Field(..., description="Number of trades executed during the interval")


class AnalyticsKline(BaseModel):
    open_time: int = Field(..., description="Opening time as a Unix timestamp in milliseconds")
    open_price: float = Field(..., description="Opening price")
    high: float = Field(..., description="Highest price in the interval")
    low: float = Field(..., description="Lowest price in the interval")
    close_price: float = Field(..., description="Closing price")
    close_time: float = Field(..., description="Closing time as Unix timestamp in milliseconds (float in example)")
    volume: float = Field(..., description="Trading volume during the interval")
    trades_num: float = Field(..., description="Number of trades executed during the interval")
    Moving_Average: Optional[float] = Field(..., alias="Moving Average", description="Calculated moving average for the interval")
    RSI: Optional[float] = Field(..., description="Relative Strength Index value")
    LowerBand: Optional[float] = Field(..., description="Lower Bollinger Band value")
    UpperBand: Optional[float] = Field(..., description="Upper Bollinger Band value")


    @validator('RSI', 'LowerBand', 'UpperBand', pre=True, always=True)
    def convert_nan_to_none(cls, v):
        if isinstance(v, float) and math.isnan(v):
            return None
        return v


    class Config:
        populate_by_name = True
        json_schema_extra = {
            "example": {
                "open_time": 1748968200000,
                "open_price": 0.2188,
                "high": 0.2197,
                "low": 0.2177,
                "close_price": 0.218,
                "close_time": 1748969999999.0,
                "volume": 234681.0,
                "trades_num": 213.0,
                "Moving Average": 0.2187749990754799,
                "RSI": 60.86956521739126,
                "LowerBand": 0.21695100402180717,
                "UpperBand": 0.22059899412915263,
            }
        }


class AnalyticsResponse(BaseModel):
    klines: List[AnalyticsKline]
    score: float = Field(..., description="Overall score as a floating point number")


class AssetPairsResponse(RootModel):
    root: Dict[str, List[str]]
