import hashlib
import uuid
import chromadb
from chromadb.utils import embedding_functions
from sentence_transformers import SentenceTransformer, CrossEncoder
from typing import List, Dict, Any, Union
import numpy as np
import faiss
import random
from rank_bm25 import BM25Okapi
from llm_hub.llm_models.api.hf_api_llm import HuggingFaceAPILLM
import pickle


class ChromaDBClient:
    """
    A wrapper for managing ChromaDB operations, including storing and retrieving vector embeddings.
    """

    def __init__(self, db_path: str = "database/wiki_rag/chroma_db", collection_name: str = "crypto_knowledge", bm25_path: str = "database/wiki_rag/bm25.pkl"):
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
        self.faiss_index = None  # faiss.IndexFlatL2()
        # self.faiss_index =
        # self.documents = []

        # BM25 Keyword-based Retrieval
        self.bm25_path = bm25_path
        self.tokenized_docs = []
        self.documents = []
        self.bm25 = None  # Will be initialized when documents are added
        # self.load_bm25()

        # Random responses when no relevant documents are found
        self.not_found_responses = [
            "I couldn't find relevant information in the knowledge base.",
            "Hmm, I couldn't find that. Try rephrasing?",
            "No luck this time! Want to ask differently?",
            "I searched, but nothing came up. Try again?",
            "That's a tricky one! Maybe another phrasing?",
            "Nothing found. Let’s give it another shot!"]

        # LLM that provides the final response
        self.llm = HuggingFaceAPILLM()

    @staticmethod
    def generate_doc_id(text: str) -> str:
        """Generate a unique and consistent ID based on document text."""
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, hashlib.sha256(text.encode()).hexdigest()))


    def add_documents(self, documents: List[Dict[str, str]]) -> None:
        """
        Batch Processing: Add documents and their embeddings to the collection.
        Metadata:
            1. title: title of the document
            2. type: [paper, article, book, other]
            3. href: link to document
            4. page_num: int
        :param documents: A list of dictionaries containing 'text' and 'source' keys.
        """
        print(f"ChromaDBClient :: Adding {len(documents)} chunks of text...")
        texts, ids, metadatas = [], [], []

        # Get existing IDs from the collection to avoid duplicates
        existing_ids = list(set(self.collection.get()["ids"]))

        for doc in documents:
            new_id = self.generate_doc_id(doc["text"])
            if new_id not in existing_ids:
                existing_ids.append(new_id)
                texts.append(doc["text"])
                ids.append(new_id)
                metadatas.append({
                    "title": doc["title"],
                    "type": doc["type"],
                    "href": doc["href"],
                    "page_num": doc["page_num"],
                })

        if len(texts) > 0:
            # Generate embeddings
            embeddings = self.embedding_model.encode(texts).tolist()

            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )

            # # Update FAISS index
            # self.faiss_index.add(np.array(embeddings).astype("float32"))
            # self.documents.extend(documents)


            # # Update BM25 retriever
            # tokenized_corpus = [doc["text"].lower().split() for doc in documents]
            # self.bm25 = BM25Okapi(tokenized_corpus)
            # Tokenize the documents for BM25 and update the BM25 model
            # Tokenize the new documents for BM25 and update the BM25 model
            # self.tokenized_docs.extend([doc.split() for doc in texts])
            # self.bm25 = BM25Okapi(self.tokenized_docs) # Update BM25 incrementally
            # self.save_bm25() # Save BM25 state to file for persistence

    def load_bm25(self):
        """
        Load the BM25 model and documents from a file for persistence.
        """
        try:
            with open(self.bm25_path, 'rb') as file:
                data = pickle.load(file)
                self.tokenized_docs = data.get('tokenized_docs', [])
                self.documents = data.get('documents', [])
                # Initialize BM25 with the existing tokenized documents
                self.bm25 = BM25Okapi(self.tokenized_docs)
                print("BM25 model loaded from file.")
        except FileNotFoundError:
            print("No BM25 model found. Starting with an empty BM25 model.")
            self.bm25 = None

    def save_bm25(self):
        """
        Save the current BM25 model and documents to a file for persistence.
        """
        with open(self.bm25_path, 'wb') as file:
            data = {
                'tokenized_docs': self.tokenized_docs,
                'documents': self.documents
            }
            pickle.dump(data, file)
            print("BM25 model saved to file.")


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
                matches.append({"text": doc, "title": meta["title"], "type": meta["type"], "href": meta["href"], "page_num": meta["page_num"]})

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


    def hybrid_similarity_search(self, query: str, n_results: int = 5) -> List[Dict[str, str]]:
        """
        Perform a hybrid search using both embeddings and BM25 for better relevance.

        :param query: The input query string.
        :param n_results: Number of results to retrieve.
        :return: List of matching documents with metadata.
        """

        hybrid_results = []

        # 1. Simple Similarity Search
        embedding_results = self.similarity_search(query, n_results=n_results)
        for doc in embedding_results:
            if doc["text"] not in [res["text"] for res in hybrid_results]:
                hybrid_results.append(doc)

        # 2. BM25 Keyword Retrieval
        if self.bm25:
            tokenized_query = query.split()
            print(self.documents)
            bm25_results = self.bm25.get_top_n(tokenized_query, self.documents, n_results)
            for doc in bm25_results:
                hybrid_results.append({"text": doc, "source": "BM25"})

        return hybrid_results


    def generate_response(self, question: str) -> str:
        """
        Sends a user query and retrieved context to a Hugging Face-hosted LLM API.

        :param question: User's query.
        :param context: Retrieved context from the knowledge base.
        :return: Generated response from the LLM.
        """

        nearest_docs = self.similarity_search(question, 3)
        context = ""
        sources = ""
        for doc in nearest_docs:
            context += doc["text"]
            sources += f"- {doc["type"]} (page: {doc["page_num"]}): {doc['title']} | {doc['href']}\n"

        prompt = f"""
            You are a knowledgeable AI assistant specialized in cryptocurrency, blockchain, and crypto technology. 
            Your goal is to provide accurate, clear, and concise answers based on the provided context. 
            If the context does not contain enough relevant information, acknowledge the limitation rather than making up an answer.
            
            ### User Query:
            {question}
            
            ### Context (Relevant Information Extracted from Documents):
            {context}
            
            ### Instructions:
            - Answer the user’s query **only using the provided context**.  
            - If the context does not contain enough information, state:  
              *"The provided information does not contain enough details to answer your question. Would you like me to suggest general insights based on my knowledge?"*  
            - Keep your response factual, direct, and professional.  
            - If necessary, reference key concepts from blockchain, DeFi, NFTs, or cryptocurrencies to clarify your answer.  
            - Use bullet points for structured explanations when helpful.  
            
            ### Response:"""

        # prompt = f"""
        # You are an AI assistant specializing in cryptocurrency.
        # Based on the following retrieved context, answer the user's question.
        # Question: {question}
        # Context: {context}
        # Provide a concise and accurate response.
        # """
        res: str = self.llm.generate_response(prompt, 4000, 0.8)

        res += f"\n\n{sources}"
        return res
