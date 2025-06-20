from typing import Annotated, Literal, List, Dict, Optional
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from langchain.chat_models.base import BaseChatModel
from langchain.chat_models import init_chat_model
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import SentenceTransformerEmbeddings
from duckduckgo_search import DDGS
from llm_gateway.agents.agent_base import AgentBase
from llm_gateway.llm_models.llm_base import LLMBase
from llm_gateway.tools.rag_retriever import DocumentRetrieverTool
from llm_gateway.tools.web_search import WebSearchTool
from dotenv import load_dotenv
import os


class MessageClassifier(BaseModel):
    message_type: Literal["technical", "web_search", "conversational"] = Field(
        ...,
        description="Classify the user query as technical (crypto concept), web_search (real-time info), or conversational (chitchat)"
    )


class State(TypedDict):
    messages: Annotated[list, add_messages]
    message_type: str | None
    next: str | None


class WikiStructuredAgent(AgentBase):
    """
    A LangGraph-based crypto assistant that routes queries to:
    - a technical agent (RAG)
    - a web search agent (DuckDuckGo)
    - a conversational agent (chitchat)

    Uses classification and retrieval to provide accurate responses.
    """

    def __init__(self, llm_model: LLMBase):
        """
        Initialize the assistant with a LangChain-compatible LLM and compile the routing graph.

        Args:
            llm: Optional LLM instance. If None, defaults to Anthropic Claude 3.5 via `init_chat_model`.
        """

        super().__init__(llm_model)

        self.llm: BaseChatModel = llm_model or init_chat_model("anthropic:claude-3-5-sonnet-latest", api_key="your_key_here")
        self.graph = self._build_graph()

        # ========================
        # TOOLS
        # ========================
        web_search = WebSearchTool(max_results=5)
        web_search_tool = web_search.as_langchain_tool()

        load_dotenv('database/db_paths.env')
        self.vectorstore_path = os.getenv("WIKI_VECTORSTORE_PATH")
        doc_retriever = DocumentRetrieverTool(
            persist_directory=self.vectorstore_path,
            collection_name="crypto_knowledge", threshold=0.5, k=5)


    def _rag_retrieve(self, query: str, threshold: float = 0.5, k: int = 5) -> List[str]:
        """
        Retrieve relevant crypto documents from a Chroma vector store.

        Args:
            query: User's question.
            threshold: Similarity threshold (0–1).
            k: Number of documents to retrieve.

        Returns:
            List of document contents as strings.
        """
        vectorstore = Chroma(
            persist_directory="/Users/nick/PycharmProjects/sibyl/database/wiki_rag/chroma_db",
            embedding_function=SentenceTransformerEmbeddings(model_name="all-MiniLM-L6-v2"),
            collection_name="crypto_knowledge"
        )
        retriever = vectorstore.as_retriever(
            search_type="similarity_score_threshold",
            search_kwargs={"score_threshold": threshold},
            k=k
        )
        results = retriever.get_relevant_documents(query)
        return [doc.page_content for doc in results] if results else []


    def _web_search(self, query: str, max_results: int = 5) -> List[str]:
        """
        Search the web using DuckDuckGo.

        Args:
            query: The user's search term.
            max_results: Max number of results to return.

        Returns:
            List of result summaries (text).
        """
        results = DDGS().text(keywords=query, max_results=max_results)
        return [r["body"] for r in results] if results else []


    def _build_graph(self):
        """
        Define and compile the LangGraph routing logic.

        Returns:
            Compiled LangGraph instance.
        """

        def classify_message(state: State) -> Dict[str, str]:
            last_message = state["messages"][-1]
            classifier_llm = self.llm.with_structured_output(MessageClassifier)

            result = classifier_llm.invoke([
                {"role": "system", "content": """
                    Classify the user query into one of three categories:
                    - 'technical': Questions about crypto concepts, protocols, or in-depth knowledge (e.g., consensus mechanisms, zero-knowledge proofs)
                    - 'web_search': Time-sensitive or factual data (e.g., current price of a coin, recent news)
                    - 'conversational': Greetings, jokes, or light conversation (e.g., "hi", "what’s up", "how are you?")
                """},
                {"role": "user", "content": last_message.content}
            ])

            return {"message_type": result.message_type}


        def technical_agent(state: State) -> Dict[str, List[Dict[str, str]]]:
            query = state["messages"][-1].content
            docs = self._rag_retrieve(query)

            if not docs or len(docs) == 0:
                return {
                    "messages": [{"role": "assistant",
                                  "content": "I couldn't find any relevant documents for that. Could you rephrase your question or ask something more specific?"}]
                }

            context = "\n\n".join(docs[:5])  # Optional: limit to avoid token overflow
            messages = [
                {
                    "role": "system",
                    "content": """You are a technical crypto assistant. Answer the user's question based **only** on the provided documentation below.
                    Use precise, technical language, and cite relevant facts when possible. Do **not** hallucinate or make up facts.
                    If the answer is not in the documents, say so clearly.
                    Documentation:
                    """
                },
                {
                    "role": "user",
                    "content": f"{context}\n\nQuestion:\n{query}"
                }
            ]
            response = self.llm.invoke(messages)
            return {"messages": [{"role": "assistant", "content": response.content}]}


        def web_search_agent(state: State) -> Dict[str, List[Dict[str, str]]]:

            query = state["messages"][-1].content
            results = self._web_search(query, 3)  # e.g., returns a list of strings or dicts

            if not results:
                return {
                    "messages": [{"role": "assistant",
                                  "content": "I couldn't find any relevant information online right now. Try rephrasing or checking back later."}]
                }

            context = "\n\n".join(results)
            messages = [
                {
                    "role": "system",
                    "content": """You are an assistant that summarizes and explains real-time search results from the web.
                    Only use the information below to answer the user. Be helpful, clear, and avoid guessing.
                    Search Results:
                    """
                },
                {
                    "role": "user",
                    "content": f"{context}\n\nUser's question:\n{query}"
                }
            ]
            response = self.llm.invoke(messages)
            return {"messages": [{"role": "assistant", "content": response.content}]}


        def conversational_agent(state: State) -> Dict[str, List[Dict[str, str]]]:
            messages = [
                {"role": "system", "content": "You are a friendly chatbot for small talk."},
                {"role": "user", "content": state["messages"][-1].content}
            ]
            reply = self.llm.invoke(messages)
            return {"messages": [{"role": "assistant", "content": reply.content}]}


        def router(state: State) -> Dict[str, str]:
            return {"next": state["message_type"]}

        graph_builder = StateGraph(State)
        graph_builder.add_node("classifier", classify_message)
        graph_builder.add_node("technical", technical_agent)
        graph_builder.add_node("web_search", web_search_agent)
        graph_builder.add_node("conversational", conversational_agent)
        graph_builder.add_node("router", router)

        graph_builder.add_edge(START, "classifier")
        graph_builder.add_edge("classifier", "router")
        graph_builder.add_conditional_edges("router", lambda state: state["message_type"], {
            "technical": "technical",
            "web_search": "web_search",
            "conversational": "conversational"
        })
        graph_builder.add_edge("technical", END)
        graph_builder.add_edge("web_search", END)
        graph_builder.add_edge("conversational", END)
        graph = graph_builder.compile()
        return graph


    def run(self, query: str) -> str:
        """
        Process a user query through the graph and return the assistant's response.

        Args:
            query: The user input as a string.

        Returns:
            Assistant's reply as a string.
        """

        state = {"messages": [], "message_type": None}
        state["messages"] = state.get("messages", []) + [{"role": "user", "content": query}]

        # state: State = {
        #     "messages": [{"role": "user", "content": query}],
        #     "message_type": None,
        #     "next": None
        # }


        final_state = self.graph.invoke(state)
        return final_state["messages"][-1].content
