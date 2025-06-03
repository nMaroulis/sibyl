from pydantic import BaseModel


class NewsChatbotResponse(BaseModel):
    chat_response: str