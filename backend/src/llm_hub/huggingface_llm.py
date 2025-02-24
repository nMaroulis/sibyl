import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from huggingface_hub import login
from backend.src.llm_hub.llm_base import LLMBase
from backend.db.api_keys_db_client import APIEncryptedDatabase
import os


class HuggingFaceLLM(LLMBase):
    """
    Implements the LLMBase for Hugging Face models.
    """

    def __init__(self, model_name: str = "gpt2", device=None): # meta-llama/Llama-3.2-3B-Instruct
        """
        Initializes a Hugging Face model.

        :param model_name: Name of the Hugging Face model.
        :param device: "cuda" or "cpu". Defaults to auto-detecting CUDA.
        """
        super().__init__(model_name, provider="huggingface")
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")

        api_creds = APIEncryptedDatabase.get_api_key_by_name("hugging_face")
        if api_creds is None:
            self.model = None
        else:
            os.environ["HF_HOME"] = api_creds.api_key
            login(token=api_creds.api_key)
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model = AutoModelForCausalLM.from_pretrained(
                model_name, torch_dtype=torch.float16, device_map="auto"
            )

    def generate_response(self, prompt: str, max_length: int = 500, temperature: float = 0.7) -> str:
        """
        Generates a response using the Hugging Face model.

        :param prompt: Input prompt.
        :param max_length: Maximum tokens in output.
        :param temperature: Sampling temperature (higher is more random).
        :return: Generated text.
        """
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        with torch.no_grad():
            output = self.model.generate(**inputs, max_length=max_length, temperature=temperature)

        return self.tokenizer.decode(output[0], skip_special_tokens=True)