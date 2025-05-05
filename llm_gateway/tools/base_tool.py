from abc import ABC, abstractmethod
from langchain.agents import Tool


class BaseTool(ABC):
    """
    Abstract base class for LangChain-compatible tools.
    Enforces a standard interface for wrapping any tool as a LangChain Tool.
    """

    # @abstractmethod
    # def run(self, query: str) -> str:
    #     """
    #     Core logic that the tool performs given a query.
    #     """
    #     pass

    @abstractmethod
    def as_langchain_tool(self) -> Tool:
        """
        Returns this tool as a LangChain Tool object.
        """
        pass

