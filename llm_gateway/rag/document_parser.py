import importlib
from llm_gateway.rag import chromadb_client
importlib.reload(chromadb_client)
from llm_gateway.rag.chromadb_client import ChromaDBClient
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
                if chunks:
                    for chunk in chunks:
                        documents.append(
                            {"title": paper.title, "type": "paper", "href":paper.pdf_url, "page_num": chunk["page_number"], "text": chunk["text"]}
                        )
        return documents

    def download_crypto_books(self):

        crypto_books = [
            {
                "title": "Cryptocurrency All-in-One For Dummies",
                "href": "https://content.e-bookshelf.de/media/reading/L-17782175-16eef2d176.pdf"
            },
            {
                "title": "Cryptocurrencies: A Guide to Getting Started",
                "href": "https://www3.weforum.org/docs/WEF_Getting_Started_Cryptocurrency_2021.pdf"
            },
            {
                "title": "Introduction to Cryptography and Cryptocurrencies",
                "href": "https://assets.press.princeton.edu/chapters/s10908.pdf"
            },
            {
                "title": "Complete Guide to Cryptocurrency Analysis",
                "href": "https://masterthecrypto.com/wp-content/uploads/2017/07/COMPLETE-GUIDE-TO-CRYPTOCURRENCY-ANALYSIS-4.pdf"
            },
            {
                "title": "Cryptoassets: The Guide to Bitcoin, Blockchain, and Cryptocurrency for Investment Professionals",
                "href": "https://www.cfainstitute.org/sites/default/files/-/media/documents/article/rf-brief/rfbr-cryptoassets.pdf"
            },
            {
                "title": "Bitcoin and Cryptocurrency Technologies: A Comprehensive Introduction",
                "href": "https://pup-assets.imgix.net/onix/images/9780691171692/9780691171692.pdf"
            },
            {
                "title": "Bitcoin and Beyond",
                "href": "https://library.oapen.org/bitstream/id/c8a35b6e-03a3-4116-97b9-af50ce7534b6/1000376.pdf"
            },
            {
                "title": "Cryptocurrency 101",
                "href": "https://www.cryptocurrency101.ph/wp-content/uploads/2018/05/FOR-PREVIEW-Cryptocurrency-101-BOOK.pdf"
            },
            {
                "title": "Investigating Cryptocurrencies",
                "href": "https://onlinelibrary.wiley.com/doi/pdf/10.1002/9781119549314.fmatter"
            },
            {
                "title": "The Crypto Encyclopedia: Coins, Tokens, and Digital Assets from A to Z",
                "href": "https://www.heg-fr.ch/media/lbdfnyd1/schueffelgroenewegbaldegger2019_crypto-encyclopedia_eng.pdf"
            },
            {
                "title": "Cryptocurrency Trading for Beginners Guide",
                "href": "https://learnpriceaction.com/wp-content/uploads/2020/08/Cryptocurrency-Trading-Beginners-Guide-PDF.pdf"
            },
            {
                "title": "Cryptocurrency All-in-One For Dummies (2022)",
                "href": "https://ia802908.us.archive.org/26/items/kiana-danial-tiana-laurence-peter-kent-tyler-bain-michael-g.-solomon-cryptocurre/Kiana%20Danial%2C%20Tiana%20Laurence%2C%20Peter%20Kent%2C%20Tyler%20Bain%2C%20Michael%20G.%20Solomon%20-%20Cryptocurrency%20All-in-One%20For%20Dummies%20%28For%20Dummies%20%28Business%20%26%20Personal%20Finance%29%29-For%20Dummies%20%282022%29.pdf"
            },
            # {
            #     "title": "The Basics of Bitcoins and Blockchains",
            #     "href": "https://bitsonblocks.net/wp-content/uploads/2018/07/the-basics-contents-draft.pdf"
            # },
        ]
        documents = []
        for i, book in enumerate(crypto_books):
            try:
                chunks = self.download_pdf(book['href'])
            except Exception as e:
                chunks = None
                print(f"{i+1} / {len(crypto_books)}: {book['title']} - FAILED")

            if chunks:
                for chunk in chunks:
                    documents.append(
                        {"title": book['title'], "type": "book", "href": book['href'], "page_num": chunk["page_number"], "text": chunk["text"]}
                    )
                print(f"{i+1} / {len(crypto_books)}: {book['title']}")
        return documents
