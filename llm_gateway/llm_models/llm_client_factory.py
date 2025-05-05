from llm_gateway.llm_models.api.hf_api_llm import HuggingFaceAPILLM
from llm_gateway.llm_models.api.openai_api_llm import OpenAIAPILLM
from llm_gateway.llm_models.api.hf_api_llm_chatbot import HuggingFaceLLMChatbot
from llm_gateway.rag.chromadb_client import ChromaDBClient
from llm_gateway.llm_models.llama_cpp.llama_cpp_llm import LlamaCppLocalLLM

# TODO Add App Factory, change llmclientfactory, for simple LLM requests, just get provider, llm_mode None -> default

class LLMClientFactory:
    _clients = {
        'hugging_face': HuggingFaceAPILLM,
        'hugging_face_chatbot': HuggingFaceLLMChatbot,
        'openai': OpenAIAPILLM,
        'wiki_rag': ChromaDBClient,
        'llama-cpp-local': LlamaCppLocalLLM,
    }

    @classmethod
    def get_client(cls, llm_api_name: str):
        client_class = cls._clients.get(llm_api_name.lower())
        if not client_class:
            raise ValueError(f"Unknown LLM API name: {llm_api_name}")
        return client_class()
