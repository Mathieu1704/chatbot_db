import os
from langchain_community.vectorstores import FAISS
from app.rag.loader import load_store
from dotenv import load_dotenv

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
_store: FAISS | None = None

def _get_store() -> FAISS:
    global _store
    if _store is None:
        _store = load_store(OPENAI_API_KEY)
    return _store

def query_sensors(query: str, k: int = 5) -> list[str]:
    """
    Retourne k passages (strings) les plus pertinents pour la requête.
    """
    docs = _get_store().similarity_search(query, k=k)
    return [d.page_content for d in docs]
