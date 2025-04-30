from abc import ABC, abstractmethod
from typing import Dict, Optional
from langchain.llms.base import LLM


class LLMBase(ABC):
    """
    Abstract base class for LLM-based services.
    Supports multiple providers (Hugging Face, OpenAI API, etc.).
    """

    def __init__(self, model_name: str, provider: str):
        """
        Initializes the LLM model.

        :param model_name: Name of the LLM model to use.
        :param provider: The LLM provider (e.g., "openai", "huggingface").
        :param api_key: Optional API key for providers that require authentication.
        """
        self.model_name = model_name
        self.provider = provider.lower()
        self.api_key = None


    @abstractmethod
    def generate_response(self, prompt: str, **kwargs) -> str:
        """
        Abstract method to generate a response from the LLM.
        Must be implemented by subclasses.

        :param prompt: The input text to the model.
        :return: Generated response as a string.
        """
        pass


    @property
    @abstractmethod
    def _llm_type(self) -> str:
        """
        local or API LLM
        """
        pass


    @abstractmethod
    def as_langchain_llm(self) -> LLM:
        pass