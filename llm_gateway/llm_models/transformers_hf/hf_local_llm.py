import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from huggingface_hub import login
from llm_gateway.llm_models.llm_base import LLMBase
from database.api_keys_db_client import APIEncryptedDatabase
import os
import platform


class HuggingFaceLocalLLM(LLMBase):
    """
    Implements the LLMBase for Hugging Face models.
    """

    def __init__(self, model_name: str = "mistralai/Mistral-7B-Instruct-v0.3", device=None): #
        """
        Initializes a Hugging Face model.

        :param model_name: Name of the Hugging Face model.
        :param device: "cuda" or "cpu". Defaults to auto-detecting CUDA.
        """
        super().__init__(model_name, provider="huggingface")

        # correctly set device - MPS for Apple silicon
        if device is None:
            if platform.system() == "Darwin" and platform.machine() == "arm64" and torch.backends.mps.is_available():
                self.device = "mps"
            else:
                self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

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
            output = self.model.generate(**inputs, temperature=temperature)

        return self.tokenizer.decode(output[0], skip_special_tokens=True)
