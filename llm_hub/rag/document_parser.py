import importlib
from llm_hub.rag import chromadb_client
importlib.reload(chromadb_client)
from llm_hub.rag.chromadb_client import ChromaDBClient
import os

# client = None  # Remove any references to ChromaDB
# import gc
# gc.collect()  # Force garbage collection

client = ChromaDBClient()

sample_documents = [
    {"text": "Bitcoin uses a Proof-of-Work consensus mechanism.", "source": "https://bitcoin.org"},
    {"text": "Ethereum switched to Proof-of-Stake consensus mechanism in 2022.", "source": "https://ethereum.org"},
    {"text": "Solana uses Proof-of-History to improve transaction speed.", "source": "https://solana.com"},
]



if client.collection_size() == 0:
    print("Adding sample documents...")
    client.add_documents(sample_documents)

print(client.collection_size())
# print(client.chroma_client.get_settings())
query_text = "How does Bitcoin validate transactions?"
results = client.similarity_search(query_text, 1)
print(f"Q: {query_text} | A:{results}")

query_text = "What consensus mechanism does Etherium?"
results = client.similarity_search(query_text, 1)
print(f"Q: {query_text} | A:{results}")


# query_text = "How does Bitcoin validate transactions?"
# results = client.hybrid_similarity_search(query_text, 1)
# print(f"Q: {query_text} | A:{results}")
#
# query_text = "What consensus mechanism does Etherium?"
# results = client.hybrid_similarity_search(query_text, 1)
# print(f"Q: {query_text} | A:{results}")
