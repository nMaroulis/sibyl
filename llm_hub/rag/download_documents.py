from llm_hub.rag.document_parser import DocumentParser
from llm_hub.rag.chromadb_client import ChromaDBClient



if __name__ == '__main__':
    client = ChromaDBClient()
    document_parser = DocumentParser()

    # ADD ARTICLES
    # docs = document_parser.download_arxiv_publications(100)
    # client.add_documents(docs)

    # ADD BOOKS
    docs = document_parser.download_crypto_books()
    client.add_documents(docs)

    # collection = client.chroma_client.get_collection("crypto_knowledge")
    # #
    # # documents = collection.get(include=["metadatas"])
    # # for i, doc in enumerate(documents["metadatas"]):
    # #     print(f"{i+1}: {doc["title"]} - {doc["type"]}")
    #
    # res = client.similarity_search("what consensus mechanism does bitcoin use?")
    # print(res)
    # #     if 'title' in doc.metadata:
    #         print(doc.metadata['title'])

    exit(0)
