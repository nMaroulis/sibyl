from openai import OpenAI
from llm_gateway.llm_models.llm_base import LLMBase
from database.api_keys_db_client import APIEncryptedDatabase
from langchain.llms.base import LLM
from langchain.llms.anthropic import Anthropic
from typing import List


class AnthropicAPILLM(LLMBase):
    """
    Implements the LLMBase for Anthropic API.
    """

    def __init__(
        self,
        model_name: str = "claude-3-7-sonnet-20250219",
        session_id: str = None,
        stream: bool = False,
    ):
        super().__init__(model_name=model_name, session_id=session_id, stream=stream)
        self.model_source = "api"
        self.model_type = "anthropic"

        api_creds = APIEncryptedDatabase.get_api_key_by_name("anthropic")
        if api_creds is None:
            self.client = None
        else:
            self.api_key = api_creds.api_key
            # init client here

    @property
    def _llm_type(self) -> str:
        return "anthropic-api"


    def initialize_model(self):
        pass


    def generate_response(self, prompt: str, max_tokens: int = 800, temperature: float = 0.7) -> str:
        """
        Generate a response using the Anthropic API.
        """
        if not self.client:
            return "⚠️ Anthropic client is not initialized (missing API key)."

        pass


    def get_available_models(self) -> List[str]:
        """
        get available models
        """
        pass


    def as_langchain_llm(self) -> LLM:
        """
        Returns a LangChain-compatible LLM.
        """
        return Anthropic(model=self.model_name, temperature=0.7, api_key=self.api_key, streaming=self.stream)
