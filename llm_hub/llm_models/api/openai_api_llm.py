import openai
from llm_hub.llm_models.llm_base import LLMBase
from database.api_keys_db_client import APIEncryptedDatabase


class OpenAIAPILLM(LLMBase):
    """
    Implements the LLMBase for OpenAI API.
    """

    def __init__(self, model_name: str = "gpt-4-turbo"):
        super().__init__(model_name, provider="openai")
        api_creds = APIEncryptedDatabase.get_api_key_by_name("openai")
        if api_creds is None:
            self.model = None
        else:
            self.api_key = api_creds.api_key

    def generate_response(self, prompt: str, max_length: int = 800, temperature: float = 0.7) -> str:
        if self.api_key is None:
            raise ValueError("OpenAI API key is missing.")

        response = openai.ChatCompletion.create(
            model=self.model_name,
            messages=[{"role": "system", "content": "You are a helpful assistant."},
                      {"role": "user", "content": prompt}],
            max_tokens=max_length,
            temperature=temperature,
            api_key=self.api_key
        )

        return response["choices"][0]["message"]["content"]