from pydantic import BaseModel
from typing import Optional


class WikiAgentRequest(BaseModel):
    model_source: str
    model_type: str
    query: str
    model_name: Optional[str] = None
    agent_type: str


class WikiAgentResponse(BaseModel):
    status: str
    data: str

class VectorStoreStatusResponse(BaseModel):
    embeddings_db: str