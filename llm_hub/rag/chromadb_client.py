import chromadb
from chromadb.utils import embedding_functions
from sentence_transformers import SentenceTransformer, CrossEncoder
from typing import List, Dict, Any, Union
import numpy as np
import faiss
import random
from rank_bm25 import BM25Okapi
# from llm_hub.llm_models.hf_api_llm import HuggingFaceAPILLM


class ChromaDBClient:
    """
    A wrapper for managing ChromaDB operations, including storing and retrieving vector embeddings.
    """

    def __init__(self, db_path: str = "database/wiki_rag/chroma_db", collection_name: str = "crypto_knowledge"):
        """
        Initialize the ChromaDB client and get or create a collection.

        :param db_path: Path to the ChromaDB storage.
        :param collection_name: Name of the collection to use.
        """
        self.chroma_client = chromadb.PersistentClient(path=db_path)
        self.collection = self.chroma_client.get_or_create_collection(collection_name)
        self.embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

        self.reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

        # FAISS Approximate Nearest Neighbor Search
        self.faiss_index = faiss.IndexFlatL2(384)  # 384-D embeddings
        self.documents = []

        # BM25 Keyword-based Retrieval
        self.bm25 = None  # Will be initialized when documents are added

        # Random responses when no relevant documents are found
        self.not_found_responses = [
            "I couldn't find relevant information in the knowledge base.",
            "Hmm, I couldn't find that. Try rephrasing?",
            "No luck this time! Want to ask differently?",
            "I searched, but nothing came up. Try again?",
            "That's a tricky one! Maybe another phrasing?",
            "Nothing found. Let’s give it another shot!"]

        # LLM that provides the final response
        self.llm = None # HuggingFaceAPILLM()

    def add_documents(self, documents: List[Dict[str, str]]) -> None:
        """
        Batch Processing: Add documents and their embeddings to the collection.

        :param documents: A list of dictionaries containing 'text' and 'source' keys.
        """
        texts = [doc["text"] for doc in documents]
        sources = [{"source": doc["source"]} for doc in documents]
        ids = [f"doc_{i}" for i in range(len(documents))]

        embeddings = self.embedding_model.encode(texts).tolist()

        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=sources,
        )

        # # Update FAISS index
        # self.faiss_index.add(np.array(embeddings).astype("float32"))
        # self.documents.extend(documents)
        #
        # # Update BM25 retriever
        # tokenized_corpus = [doc["text"].lower().split() for doc in documents]
        # self.bm25 = BM25Okapi(tokenized_corpus)

    def collection_size(self) -> int:
        """
        Get the number of documents in the collection.

        :return: Number of stored documents.
        """
        return self.collection.count()

    def similarity_search(self, query: str, n_results: int = 5) -> List[Dict[str, str]]:
        """
        Perform a similarity search using embeddings.

        :param query: The input query string.
        :param n_results: Number of results to retrieve.
        :return: List of matching documents with metadata.
        """

        query_embedding = self.embedding_model.encode([query]).tolist()
        results = self.collection.query(
            query_embeddings=query_embedding, n_results=n_results, include=["documents", "metadatas"]
        )

        # Format results
        matches = []
        if results.get("documents"):
            for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
                matches.append({"text": doc, "source": meta["source"]})

        return matches

    def hybrid_search(self, query: str, top_k: int = 3, relevance_threshold: float = 0.5) -> Union[str, Dict[str, Any]]:
        """
        Performs hybrid retrieval using ChromaDB, FAISS, and BM25.
        Then reranks results and filters out low-confidence matches.

        :param query: User query string.
        :param top_k: Number of top results to retrieve from each method.
        :param relevance_threshold: Minimum reranker score to accept a result.
        :return: Best-matching document or a message if no relevant information is found.
        """
        query_embedding: List[float] = self.embedding_model.encode(query).tolist()

        # Step 1: Retrieve top-K results from ChromaDB (vector search)
        results = self.collection.query(
            query_embeddings=[query_embedding], n_results=top_k, include=["documents", "metadatas", "distances"]
        )

        # Step 2: FAISS Approximate Nearest Neighbor search
        _, faiss_indices = self.faiss_index.search(np.array([query_embedding]).astype("float32"), top_k)
        faiss_results: List[str] = [self.documents[i]["text"] for i in faiss_indices[0]]

        # Step 3: BM25 keyword-based retrieval
        bm25_scores = self.bm25.get_scores(query.lower().split())
        bm25_top_indices = np.argsort(bm25_scores)[-top_k:][::-1]
        bm25_results: List[str] = [self.documents[i]["text"] for i in bm25_top_indices]

        # Step 4: Merge results from all retrieval methods
        merged_results: List[str] = list(set(results["documents"][0] + faiss_results + bm25_results))
        merged_metadata: List[Dict[str, str]] = results["metadatas"][0]

        if not merged_results:
            return random.choice(self.not_found_responses)

        # Step 5: Rerank using a cross-encoder model
        query_doc_pairs = [(query, doc) for doc in merged_results]
        rerank_scores = self.reranker.predict(query_doc_pairs)

        # Step 6: Select the best match based on the reranker score
        best_match_index = np.argmax(rerank_scores)
        best_match_score = rerank_scores[best_match_index]

        if best_match_score < relevance_threshold:
            return random.choice(self.not_found_responses)

        best_document = merged_results[best_match_index]
        best_metadata = merged_metadata[best_match_index] if best_match_index < len(merged_metadata) else {}

        return {
            "answer": best_document,
            "source": best_metadata.get("source", "Unknown"),
            "score": best_match_score,
        }

    def get_final_response(self, question: str, context: str) -> str:
        """
        Sends a user query and retrieved context to a Hugging Face-hosted LLM API.

        :param question: User's query.
        :param context: Retrieved context from the knowledge base.
        :return: Generated response from the LLM.
        """

        prompt = f"""
        You are an AI assistant specializing in cryptocurrency.
        Based on the following retrieved context, answer the user's question.

        Question: {question}
        Context: {context}

        Provide a concise and accurate response.
        """

        res: str = self.llm.generate_response(prompt, 1200, 0.9)
        return res
