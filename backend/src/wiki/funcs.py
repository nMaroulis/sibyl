import os
from database.api_keys_db_client import APIEncryptedDatabase

CHROMA_DB_PATH = "database/wiki_rag/chroma_db"


def check_exists_chroma_db() -> str:
    return "yes" if os.path.isdir(CHROMA_DB_PATH) else "no"


def check_exists_llm_api(llm_model: str) -> str:
    api_creds = APIEncryptedDatabase.get_api_key_by_name(llm_model)
    return "yes" if api_creds else "no"
