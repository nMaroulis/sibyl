from huggingface_hub import InferenceClient
from database.api_keys_db_client import APIEncryptedDatabase


class HuggingFaceLLMChatbot:
    def __init__(self, model_name: str = "mistralai/Mistral-7B-Instruct-v0.3"):
        api_creds = APIEncryptedDatabase.get_api_key_by_name("hugging_face")
        if api_creds is None:
            self.client = None
        else:
            self.client = InferenceClient(model_name, token=api_creds.api_key)


    def generate_response(self, prompt: str, max_new_tokens: int = 250, temperature: float = 0.7):
        response = self.client.text_generation(prompt, max_new_tokens=max_new_tokens, temperature=temperature)
        return response
