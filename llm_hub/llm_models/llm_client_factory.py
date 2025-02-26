from llm_hub.llm_models.hf_api_llm import HuggingFaceAPILLM
from llm_hub.llm_models.hf_api_llm_chatbot import HuggingFaceLLMChatbot

class LLMClientFactory:
    _clients = {
        'hugging_face': HuggingFaceAPILLM,
        'hugging_face_chatbot': HuggingFaceLLMChatbot,
    }

    @classmethod
    def get_client(cls, llm_api_name: str):
        client_class = cls._clients.get(llm_api_name.lower())
        if not client_class:
            raise ValueError(f"Unknown LLM API name: {llm_api_name}")
        return client_class()
