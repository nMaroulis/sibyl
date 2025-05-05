from langchain.agents import Tool
from duckduckgo_search import DDGS
from llm_gateway.tools.base_tool import BaseTool


class WebSearchTool(BaseTool):
    """
    Class to perform a web search using DuckDuckGo and return the top results.
    This can be used as a LangChain tool for an agent.

    # Example usage
    web_search = WebSearchTool(max_results=5)
    web_search_tool = web_search.as_langchain_tool()
    """

    def __init__(self, max_results: int = 5):
        """
        Initializes the WebSearchTool with the number of results to retrieve.
        """
        self.max_results = max_results


    def search(self, query: str) -> str:
        """
        Perform a web search using DuckDuckGo and return the top results.
        """
        results = DDGS().text(keywords=query, max_results=self.max_results)
        return "\n".join([r["body"] for r in results]) if results else "No web results found."


    def as_langchain_tool(self) -> Tool:
        """
        Converts the WebSearchTool class into a LangChain Tool.
        """
        return Tool(
            name="WebSearch",
            func=self.search,
            description="Use to search the web when document search fails or lacks context."
        )
