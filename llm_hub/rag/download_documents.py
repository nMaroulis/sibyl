from llm_hub.rag.document_parser import DocumentParser
from llm_hub.rag.chromadb_client import ChromaDBClient



if __name__ == '__main__':
    client = ChromaDBClient()
    document_parser = DocumentParser()
    docs = document_parser.download_arxiv_publications(1)
    client.add_documents(docs)
