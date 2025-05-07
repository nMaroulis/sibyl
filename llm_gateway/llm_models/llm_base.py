from abc import ABC, abstractmethod
from typing import Dict, Optional
from langchain.llms.base import LLM


class LLMBase(ABC):
    """
    Abstract base class for LLM-based services.
    Supports multiple providers (Hugging Face, OpenAI API, etc.).
    """

    def __init__(self, model_name: str, session_id: str = None, stream: bool = False):
        """
        LLM model params.

        Args:
            model_name (str): Name of the model to use (e.g., "mistralai/Mistral-7B-Instruct-v0.2").
            session_id (Optional[str]): Session identifier for tracking.
            stream (bool): Whether to enable streaming responses.

        Params:
            :param string model_source = 1; // "local" or "api"
            :param string model_type = 2;   // e.g. "llama-cpp", "hugging-face", "tgi"
            :param optional string model_name = 3;   // e.g. "llama-3-8b-instruct", "mistralai/Mistral-7B-Instruct-v0.2"
            :param optional string session_id = 4;
            :param optional bool stream = 5;
            :param string input_text = 6;   // the user's query or input
        """
        self.model_source: str = ""
        self.model_type: str = ""
        self.model_name: str = model_name
        self.session_id: str = session_id
        self.stream: bool = stream
        self.api_key: str = ""


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