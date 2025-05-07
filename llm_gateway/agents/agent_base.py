from abc import ABC, abstractmethod
from llm_gateway.llm_models.llm_base import LLMBase


class AgentBase(ABC):
    """
    Abstract base class for Agents.
    """

    def __init__(self, llm_model: LLMBase):
        """
        """
        self.agent_name = ""
        self.tools = []
        self.llm = None # llm_model.as_langchain_llm()


    @abstractmethod
    def run(self, query: str) -> str:
        """
        """
        pass
