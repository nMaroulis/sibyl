from huggingface_hub import InferenceClient
from llm_gateway.llm_models.llm_base import LLMBase
from database.api_keys_db_client import APIEncryptedDatabase
from langchain.llms.base import LLM
from langchain_community.llms import HuggingFaceHub

class HuggingFaceAPILLM(LLMBase):
    """
    Implements the LLMBase for Hugging Face API.
    """

    def __init__(self, model_name: str = "mistralai/Mistral-7B-Instruct-v0.3"): #

        super().__init__(model_name, provider="huggingface")
        api_creds = APIEncryptedDatabase.get_api_key_by_name("hugging_face")
        if api_creds is None:
            self.model = None
        else:
            self.model = InferenceClient(model_name, token=api_creds.api_key)
            # self.api = api_creds.api_key


    @property
    def _llm_type(self) -> str:
        return "huggingface-api"


    def generate_response(self, prompt: str, max_length: int = 800, temperature: float = 0.8) -> str:

        response = self.model.text_generation(prompt, max_new_tokens=max_length, temperature=0.8)
        return response


    def as_langchain_llm(self) -> LLM:

        return LLM.from_callable(lambda prompt, stop=None, **kwargs: self.generate_response(prompt), llm_type="huggingface-api")
        # return HuggingFaceHub(
        #         repo_id="mistralai/Mistral-7B-Instruct-v0.3",  # or your model
        #         model_kwargs={"temperature": 0.9, "max_length": 4096},
        #         huggingfacehub_api_token=self.api
        #     )
