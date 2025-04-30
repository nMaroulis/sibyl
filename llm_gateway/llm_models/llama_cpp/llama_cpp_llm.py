from llama_cpp import Llama
from langchain.llms.base import LLM
from llm_gateway.llm_models.llm_base import LLMBase
from dotenv import load_dotenv
import os


class LlamaCppLocalLLM(LLMBase):
    """
    Local LLM using llama.cpp, wrapped for LangChain compatibility.
    """

    def __init__(self, model_path: str = "/llm_gateway/llm_models/llama_cpp/models/mistral-7b-instruct-v0.1.Q4_K_M.gguf"):
        super().__init__(model_name="llama-cpp", provider="local")
        load_dotenv("llm_gateway/config.env")
        model_path = os.getenv("LLAMA_CPP_LLM_MODEL_PATH")
        self.model = Llama(
            model_path=model_path,
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


    def as_langchain_llm(self) -> LLM:

        return LLM.from_callable(
            lambda prompt, stop=None, **kwargs: self.generate_response(prompt),
            llm_type="llama-cpp-local"
        )
