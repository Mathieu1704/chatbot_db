"""
Indexe (ou ré-indexe) les documents network_nodes d'une entreprise
sous forme de vecteurs pour permettre des requêtes sémantiques.
On stocke FAISS sur disque (<project>/app/rag/store_{company}.faiss)
pour accélérer le démarrage et supporter plusieurs entreprises.
"""
import os
import json
import pickle
from dotenv import load_dotenv
from app.db import get_nodes_collection
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS

load_dotenv()

# Chemins génériques utilisant le nom de l'entreprise
BASE_DIR = os.path.dirname(__file__)

def _get_store_paths(company: str):
    """Retourne (store_path, meta_path) spécifiques à l'entreprise"""
    filename = company.replace(' ', '_').lower()
    store_path = os.path.join(BASE_DIR, f"store_{filename}.faiss")
    meta_path  = os.path.join(BASE_DIR, f"store_{filename}.meta")
    return store_path, meta_path


def _docs_from_mongo(company: str):
    """Transforme chaque capteur en un blob texte + métadonnées."""
    nodes = get_nodes_collection(company)
    docs = []
    for n in nodes.find({}, {"_id": 0}):
        blob = (
            f"Capteur {n.get('address')} (parent {n.get('parent')}) – "
            f"batterie {n.get('batt')} mV, RSSI {n.get('rssi')} dBm. "
            f"Dernière communication {n.get('last_com')}"
        )
        docs.append(json.dumps({"text": blob, **n}, default=str))
    return docs


def build_store(api_key: str, company: str):
    """Construit et sauvegarde l'index FAISS pour une entreprise."""
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    raw_docs = _docs_from_mongo(company)

    splitter = RecursiveCharacterTextSplitter(chunk_size=256, chunk_overlap=32)
    chunks = [c for doc in raw_docs for c in splitter.split_text(doc)]

    emb = OpenAIEmbeddings(openai_api_key=api_key)
    store = FAISS.from_texts(chunks, emb)

    store_path, meta_path = _get_store_paths(company)
    store.save_local(store_path)
    with open(meta_path, 'wb') as f:
        pickle.dump({"count": len(raw_docs)}, f)


def load_store(api_key: str, company: str) -> FAISS:
    """Charge (ou construit) l'index FAISS pour l'entreprise donnée."""
    emb = OpenAIEmbeddings(openai_api_key=api_key)
    store_path, _ = _get_store_paths(company)
    if not os.path.exists(store_path):
        build_store(api_key, company)
    return FAISS.load_local(store_path, emb)
