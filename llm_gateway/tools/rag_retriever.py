from langchain.agents import Tool
from vectorstore.chroma import get_vectorstore

store = get_vectorstore()

def search_docs(query: str) -> str:
    docs = store.similarity_search(query, k=3)
    return "\n".join([doc.page_content for doc in docs]) if docs else "No relevant documents found."

search_tool = Tool(
    name="SearchDocs",
    func=search_docs,
    description="Use to search internal documents for answers."
)
