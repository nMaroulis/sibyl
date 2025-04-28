import chromadb
from chromadb.config import Settings

class RagRetriever:
    def __init__(self, persist_directory="./chroma_db"):
        self.client = chromadb.Client(Settings(
            persist_directory=persist_directory,
            chroma_db_impl="duckdb+parquet",
            anonymized_telemetry=False
        ))
        self.collection = self.client.get_or_create_collection(name="default")

    def retrieve(self, query: str, n_results: int = 5) -> list:
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results
        )
        return [doc for doc in results['documents'][0]]
