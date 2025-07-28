# # app/search/run_query.py
# """
# run_query(db_name, coll, query, filter_json=None, k=10)
# → Retourne k documents après recherche vectorielle + filtres
# """

# import os, json
# from functools import lru_cache
# from datetime import datetime, timezone
# from dotenv import load_dotenv
# from pymongo import MongoClient
# from typing import Union, Optional, List, Dict
# from sentence_transformers import SentenceTransformer

# load_dotenv()
# client = MongoClient(os.getenv("MONGODB_URI"))

# MODEL_NAME   = "all-MiniLM-L6-v2"
# DIMENSION    = 384
# VECTOR_INDEX = "vector_index"   # nom exact dans Atlas

# @lru_cache(maxsize=1)
# def _get_model():
#     return SentenceTransformer(MODEL_NAME, device="cuda")

# def _encode(text: str) -> list[float]:
#     return _get_model().encode(text).tolist()

# def run_query(
#     db_name: str,
#     coll: str,
#     query: str,
#     filter_json: dict | None = None,
#     k: int | None = None,
#     num_candidates: int | None = None,
#     projection: dict | None = None,
#     index_name: str | None = None,
# ) -> List[dict]:
#     """
#     Effectue une recherche sémantique MongoDB ($vectorSearch).

#     Parameters
#     ----------
#     query : str
#         Texte en langage naturel.
#     filter_json : dict, optional
#         Filtres MongoDB (ex. {"batt": {"$lt": 3500}}).
#     k : int, default 10
#         Nombre de documents retournés.
#     num_candidates : int, optional
#         Taille du candidate set. Défaut = k*40.
#     projection : dict, optional
#         Projection MongoDB (ex. {"embedding": 0}).  Si None, masque l'embedding.
#     index_name : str, optional
#         Nom de l’index vectoriel. Défaut = `VECTOR_INDEX`.

#     Returns
#     -------
#     list[dict]
#     """
#     vect = _encode(query)

#     MAX_CANDIDATES = 10_000  
    
#     k = k or 100                              # valeur plancher si None
#     n = num_candidates or k * 40              # heuristique
#     n = min(n, MAX_CANDIDATES) 

#     pipe = [{
#         "$vectorSearch": {
#             "index": index_name or VECTOR_INDEX,
#             "path": "embedding",
#             "queryVector": vect,
#             "limit": k,
#             "numCandidates": n,
#             "filter": filter_json or {}
#         }
#     }]

#     # Masquer l'embedding par défaut pour alléger la charge
#     if projection is None:
#         projection = {"embedding": 0}

#     pipe.append({"$project": projection})

#     try:
#         docs = list(
#             client[db_name][coll].aggregate(
#                 pipe,
#                 allowDiskUse=False
#             )
#         )
#     except Exception as exc:
#         raise RuntimeError(f"Vector search failed: {exc}") from exc

#     # Conversion BSON → JSON-serialisable
#     return json.loads(json.dumps(docs, default=str))

