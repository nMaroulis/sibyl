from openai import OpenAI
from llm_gateway.llm_models.llm_base import LLMBase
from database.api_keys_db_client import APIEncryptedDatabase
from langchain.llms.base import LLM
from langchain_openai import ChatOpenAI
from typing import List

class OpenAIAPILLM(LLMBase):
    """
    Implements the LLMBase for OpenAI API.
    """

    def __init__(
        self,
        model_name: str = "gpt-4-turbo",
        session_id: str = None,
        stream: bool = False,
    ):
        super().__init__(model_name=model_name, session_id=session_id, stream=stream)
        self.model_source = "api"
        self.model_type = "openai"

        api_creds = APIEncryptedDatabase.get_api_key_by_name("openai")
        if api_creds is None:
            self.client = None
        else:
            self.api_key = api_creds.api_key
            self.client = OpenAI(api_key=self.api_key)

    @property
    def _llm_type(self) -> str:
        return "openai-api"

    def generate_response(self, prompt: str, max_tokens: int = 800, temperature: float = 0.7) -> str:
        """
        Generate a response using the OpenAI API.
        """
        if not self.client:
            return "⚠️ OpenAI client is not initialized (missing API key)."

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            stream=self.stream,
        )

        if self.stream:
            return "".join(chunk.choices[0].delta.get("content", "") for chunk in response)
        return response.choices[0].message.content


    def get_available_models(self) -> List[str]:
        """
        get available models
        """
        pass


    def as_langchain_llm(self) -> LLM:
        """
        Returns a LangChain-compatible LLM.
        """
        return ChatOpenAI(model=self.model_name, temperature=0.7, api_key=self.api_key, streaming=self.stream)
