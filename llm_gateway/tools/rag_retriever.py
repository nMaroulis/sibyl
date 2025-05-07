from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain.agents import Tool
from typing import List
from llm_gateway.tools.base_tool import BaseTool



class DocumentRetrieverTool(BaseTool):
    """
    LangChain-compatible tool for retrieving crypto-related documents from a Chroma vector store.

    # Example usage:
    doc_retriever = DocumentRetrieverTool(threshold=0.5, k=5)
    doc_retriever_tool = doc_retriever.as_langchain_tool()
    """
    def __init__(
            self,
            persist_directory: str,
            collection_name: str,
            embedding_model_name: str = "all-MiniLM-L6-v2",
            k: int = 5,
            threshold: float = 0.5
    ):
        """
        Initialize the Chroma vector store and embedder.

        Args:
            persist_directory: Path to Chroma DB.
            collection_name: Name of the Chroma collection.
            embedding_model_name: Name of the SentenceTransformer model.
            k: Number of documents to retrieve.
            threshold: Minimum similarity score (0-1) for filtering results.
        """
        self.k = k
        self.threshold = threshold

        self.vectorstore = Chroma(
            persist_directory=persist_directory,
            embedding_function=SentenceTransformerEmbeddings(model_name=embedding_model_name),
            collection_name=collection_name
        )


    def retrieve(self, query: str) -> List[str]:
        """
        Retrieve relevant documents for a given query.
        Returns concatenated content or fallback message.
        """
        retriever = self.vectorstore.as_retriever(
            search_type="similarity_score_threshold",
            search_kwargs={"score_threshold": self.threshold},
            k=self.k
        )

        results = retriever.get_relevant_documents(query)

        # Return the document content (or empty if no results found)
        return [doc.page_content for doc in results] if results else []


    def as_langchain_tool(self) -> Tool:
        """
        Convert to a LangChain-compatible Tool.
        """
        return Tool(
            name="DocumentRetriever",
            func=self.retrieve,
            description="Use to retrieve crypto-related knowledge from a vector store."
        )
