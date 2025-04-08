from llm_hub.llm_models.api.hf_api_llm import HuggingFaceAPILLM
from llm_hub.llm_models.api.openai_api_llm import OpenAIAPILLM
from llm_hub.llm_models.api.hf_api_llm_chatbot import HuggingFaceLLMChatbot
from llm_hub.rag.chromadb_client import ChromaDBClient


class LLMClientFactory:
    _clients = {
        'hugging_face': HuggingFaceAPILLM,
        'hugging_face_chatbot': HuggingFaceLLMChatbot,
        'openai': OpenAIAPILLM,
        'wiki_rag': ChromaDBClient,
    }

    @classmethod
    def get_client(cls, llm_api_name: str):
        client_class = cls._clients.get(llm_api_name.lower())
        if not client_class:
            raise ValueError(f"Unknown LLM API name: {llm_api_name}")
        return client_class()
