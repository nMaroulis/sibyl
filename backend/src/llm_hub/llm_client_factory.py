from backend.src.llm_hub.huggingface_api_llm import HuggingFaceAPILLM

class LLMClientFactory:
    _clients = {
        'hugging_face': HuggingFaceAPILLM,
    }

    @classmethod
    def get_client(cls, llm_api_name: str):
        client_class = cls._clients.get(llm_api_name.lower())
        if not client_class:
            raise ValueError(f"Unknown LLM API name: {llm_api_name}")
        return client_class()
