from mcp_server.llm_client import LLMClient
from mcp_server.tools.rag_retriever import RagRetriever
from mcp_server.tools.memory_store import MemoryStore
from mcp_server.tools.web_search_brave import WebSearchTool
import asyncio

class AgentPipeline:
    def __init__(self, brave_api_key: str):
        self.llm_client = LLMClient()
        self.rag_retriever = RagRetriever()
        self.memory_store = MemoryStore()
        self.web_search = WebSearchTool(brave_api_key)

    async def handle_query(self, user_id: str, query: str) -> str:
        # Save user query in memory
        self.memory_store.add_memory(user_id, {"user": query})

        # Step 1: Check if it's conversational (small heuristic)
        if len(query.split()) <= 4:
            prompt = f"Have a friendly conversation. User said: {query}"
            response = await asyncio.to_thread(self.llm_client.generate, prompt)
        else:
            # Step 2: Try RAG
            documents = await asyncio.to_thread(self.rag_retriever.retrieve, query)
            if documents:
                context = "\n".join(documents)
                prompt = f"Use this context to answer: {context}\n\nQuestion: {query}"
                response = await asyncio.to_thread(self.llm_client.generate, prompt)
            else:
                # Step 3: Fall back to Web Search
                search_summary = await asyncio.to_thread(self.web_search.search, query)
                prompt = f"Use this web search summary to answer: {search_summary}\n\nQuestion: {query}"
                response = await asyncio.to_thread(self.llm_client.generate, prompt)

        # Save LLM response to memory
        self.memory_store.add_memory(user_id, {"assistant": response})

        return response
