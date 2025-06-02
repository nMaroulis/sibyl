from datetime import datetime
from typing import List, Optional, Union
from pydantic import BaseModel


class BitcoinBlock(BaseModel):
    Block_Height: int
    Date: datetime
    Transaction_Count: int
    Block_Size: float  # in KB
    Block_Weight: int
    Difficulty: Union[int, float]  # Some APIs return difficulty as float


class LitecoinBlock(BaseModel):
    Date: datetime
    Block_Time_min: Optional[float] = None
    Transaction_Count: int
    Transaction_Fee_LTC: Optional[float] = None


class BlockchainBlockResponse(BaseModel):
    status: str
    data: List[Union[BitcoinBlock, LitecoinBlock]]
