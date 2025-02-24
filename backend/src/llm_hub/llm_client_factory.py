from backend.src.llm_hub.huggingface_llm import HuggingFaceLLM

class LLMClientFactory:
    _clients = {
        'hugging_face': HuggingFaceLLM,
    }

    @classmethod
    def get_client(cls, llm_api_name: str):
        client_class = cls._clients.get(llm_api_name.lower())
        if not client_class:
            raise ValueError(f"Unknown LLM API name: {llm_api_name}")
        return client_class()
