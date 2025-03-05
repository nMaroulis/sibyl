import importlib
from llm_hub.rag import chromadb_client
importlib.reload(chromadb_client)
from llm_hub.rag.chromadb_client import ChromaDBClient
import os
import requests
import pymupdf
import re, unicodedata
from sentence_transformers import SentenceTransformer
import math
import arxiv

class DocumentParser:

    def __init__(self):
        # Load the Sentence Transformer model tokenizer
        self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.tokenizer = self.model.tokenizer


    @staticmethod
    def clean_text(text: str) -> str:
        """Cleans text by removing extra spaces, special characters, and normalizing Unicode."""
        text = re.sub(r'http[s]?://\S+|www\.\S+', '', text) # remove hyperlinks
        text = unicodedata.normalize("NFKC", text)  # Normalize Unicode characters
        text = re.sub(r"<[^>]+>", "", text)  # Remove HTML tags
        text = re.sub(r"\s+", " ", text).strip()  # Remove extra spaces and newlines
        return text


    def chunk_text_with_overlap(self, text: str, chunk_size: int =312, overlap: int =64):
        # Tokenize the document text
        tokens = self.tokenizer.encode(text, truncation=False, padding=False)

        # Calculate the number of chunks required
        num_chunks = math.ceil(len(tokens) / (chunk_size - overlap))

        chunks_with_page_info = []

        # Create chunks with overlap
        for i in range(num_chunks):
            start = i * (chunk_size - overlap)
            end = start + chunk_size
            chunk_tokens = tokens[start:end]

            # Decode tokens back to text
            chunk_text = self.tokenizer.decode(chunk_tokens, skip_special_tokens=True)

            chunks_with_page_info.append(chunk_text)

        return chunks_with_page_info


    def download_pdf(self, pdf_url: str):

        response = requests.get(pdf_url)
        if response.status_code == 200:
            doc = pymupdf.open("pdf", response.content)

            chunks_with_page_info = []

            # Process each page in the PDF
            for page_number in range(doc.page_count):
                page = doc.load_page(page_number)
                page_text = page.get_text("text")
                page_text = self.clean_text(page_text)

                # Chunk the page's text
                page_chunks = self.chunk_text_with_overlap(page_text)

                # Append chunks with page number
                for chunk in page_chunks:
                    if len(chunk) > 50: # minimum chunk size threshold
                        chunks_with_page_info.append({
                            "text": chunk,
                            "page_number": page_number + 1  # Page numbers to start from 1
                        })
            return chunks_with_page_info

        else:
            return None


    def download_arxiv_publications(self, num_results: int = 20):

        arxiv_client = arxiv.Client()
        documents = []

        searches = ["cryptocurrency OR blockchain", "DeFi OR NFT"]
        for s in searches:
            search = arxiv.Search(query=s, max_results=num_results)
            for paper in arxiv_client.results(search):
                print(paper.pdf_url)
                chunks = self.download_pdf(paper.pdf_url)
                for chunk in chunks:
                    documents.append(
                        {"title": paper.title, "type": "paper", "href":paper.pdf_url, "page_num": chunk["page_number"], "text": chunk["text"]}
                    )

        return documents
