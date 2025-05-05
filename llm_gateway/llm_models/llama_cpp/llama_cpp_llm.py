from llama_cpp import Llama
from llm_gateway.llm_models.llm_base import LLMBase
from dotenv import load_dotenv
import os
from langchain.llms import LlamaCpp


class LlamaCppLocalLLM(LLMBase):
    """
    Local LLM using llama.cpp, wrapped for LangChain compatibility.
    """

    def __init__(self):
        super().__init__(model_name="llama-cpp", provider="local")
        load_dotenv("llm_gateway/llm_models/config.env")
        self.model_path = os.getenv("LLAMA_CPP_LLM_MODEL_PATH")
        self.model = Llama(
            model_path=self.model_path,
            n_ctx=4096,
            n_threads=4,
            n_gpu_layers=20,
            verbose=False
        )


    @property
    def _llm_type(self) -> str:
        return "llama-cpp-local"


    def generate_response(self, prompt: str, max_tokens: int = 800, temperature: float = 0.7) -> str:
        response = self.model(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=["</s>", "USER:", "ASSISTANT:"],  # Customize for your prompt format
        )
        return response["choices"][0]["text"].strip()


    def as_langchain_llm(self) -> LlamaCpp:
        return LlamaCpp(model_path=self.model_path, temperature=0.9, max_tokens=4096, n_gpu_layers=20, f16_kv=True)

