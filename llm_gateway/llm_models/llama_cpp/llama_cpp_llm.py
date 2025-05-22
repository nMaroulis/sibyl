from llama_cpp import Llama
from llm_gateway.llm_models.llm_base import LLMBase
from dotenv import load_dotenv
import os
from langchain_community.llms import LlamaCpp
from typing import List


CONTEXT_WINDOW_DICT = {
    "openhermes-2.5-mistral-7b.Q4_K_M": 4096, # 32768,
}

class LlamaCppLocalLLM(LLMBase):
    """
    Implements the LLMBase for llama.cpp.
    """

    def __init__(self, model_name: str = "openhermes-2.5-mistral-7b.Q4_K_M", session_id: str = None, stream: bool = False):
        super().__init__(model_name=model_name, session_id=session_id, stream=stream)
        self.model_source = "local"
        self.model_type = "llama_cpp"
        load_dotenv("llm_gateway/llm_models/config.env")

        if model_name.endswith(".gguf"): # Remove extension if found in the name TODO - fix
            self.model_name = model_name[:-5]
        self.model_path = f"{os.getenv("LLAMA_CPP_LLM_MODEL_PATH")}{self.model_name}.gguf"
        self.model = None


    def initialize_model(self):
        if os.path.exists(self.model_path):

            self.model = Llama(
                model_path=self.model_path,
                n_ctx=CONTEXT_WINDOW_DICT.get(self.model_name, 4096),
                n_threads=4,
                n_gpu_layers=20,
                verbose=False
            )
        else:
            self.model = None


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


    def get_available_models(self) -> List[str]:
        return [f for f in os.listdir(os.getenv("LLAMA_CPP_LLM_MODEL_PATH")) if f.lower().endswith(".gguf")]


    def as_langchain_llm(self) -> LlamaCpp:

        return LlamaCpp(
            model_path=self.model_path,
            temperature=0.9,
            max_tokens=CONTEXT_WINDOW_DICT.get(self.model_name, 4096),
            n_ctx=CONTEXT_WINDOW_DICT.get(self.model_name, 4096),  # <-- Add this
            context_window=CONTEXT_WINDOW_DICT.get(self.model_name, 4096),
            n_gpu_layers=20,
            f16_kv=True,
            cache=False, # Stateless Run
        )
