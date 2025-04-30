from langchain.agents import Tool
from duckduckgo_search import DDGS

def search_web(query: str) -> str:
    results = DDGS().text(keywords=query, max_results=5)
    return "\n".join([r["body"] for r in results]) if results else "No web results found."

web_search_tool = Tool(
    name="WebSearch",
    func=search_web,
    description="Use when document search fails or lacks context."
)
