from llm_gateway.llm_models.api.hf_api_llm import HuggingFaceAPILLM
from llm_gateway.llm_models.api.openai_api_llm import OpenAIAPILLM
from llm_gateway.llm_models.llama_cpp.llama_cpp_llm import LlamaCppLocalLLM
from llm_gateway.llm_models.llm_base import LLMBase
from typing import Optional


class LLMClientFactory:
    _clients = {
        'hugging_face': HuggingFaceAPILLM,
        'openai': OpenAIAPILLM,
        'llama_cpp': LlamaCppLocalLLM,
    }

    @classmethod
    def get_client(cls, model_type: str, model_name: Optional[str] = None, stream: bool = False) -> LLMBase:
        client_class = cls._clients.get(model_type.lower())
        if not client_class:
            raise ValueError(f"Unknown LLM API name: {model_type}")
        return client_class() if model_name is None else client_class(model_name=model_name)
