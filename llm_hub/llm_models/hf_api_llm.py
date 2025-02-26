from huggingface_hub import InferenceClient
from llm_hub.llm_models.llm_base import LLMBase
from database.api_keys_db_client import APIEncryptedDatabase


class HuggingFaceAPILLM(LLMBase):
    """
    Implements the LLMBase for Hugging Face API.
    """

    def __init__(self, model_name: str = "mistralai/Mistral-7B-Instruct-v0.3"): #

        super().__init__(model_name, provider="huggingface")
        api_creds = APIEncryptedDatabase.get_api_key_by_name("hugging_face")
        if api_creds is None:
            self.model = None
        else:
            self.model = InferenceClient(model_name, token=api_creds.api_key)

    def generate_response(self, prompt: str, max_length: int = 800, temperature: float = 0.7) -> str:

        response = self.model.text_generation(prompt, max_new_tokens=max_length, temperature=0.7)
        return response
