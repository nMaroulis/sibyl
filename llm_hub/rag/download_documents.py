from llm_hub.rag.document_parser import DocumentParser
from llm_hub.rag.chromadb_client import ChromaDBClient



if __name__ == '__main__':
    client = ChromaDBClient()
    document_parser = DocumentParser()
    docs = document_parser.download_arxiv_publications(100)
    client.add_documents(docs)

    docs = document_parser.download_crypto_books()
    client.add_documents(docs)
    # collection = client.chroma_client.get_collection("crypto_knowledge")
    # documents = collection.get(include=["metadatas"])
    # print(documents)
    # for doc in documents['documents']:
    #     if 'title' in doc.metadata:
    #         print(doc.metadata['title'])
