import os
import json
from functools import lru_cache
from dotenv import load_dotenv
from pymongo import MongoClient, errors
from app.utils.slugify_company import slugify_company
from typing import Optional, Dict, Any, List
import difflib


# Charger .env
load_dotenv()

# Puis, juste :
MONGODB_URI = os.getenv("MONGODB_URI")
client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5_000)

try:
    client.admin.command("ping")
    print(f"[INFO] MongoDB reachable via {MONGODB_URI}")
except errors.PyMongoError as exc:
    raise RuntimeError(f"Mongo unreachable: {exc}") from exc



def get_nodes_collection(company: str):
    """
    Retourne la collection `network_nodes` de la base MongoDB `company`.
    """
    return client[company]["network_nodes"]

@lru_cache(maxsize=1)
def list_companies() -> list[str]:
    """
    Renvoie la liste des noms de bases qui contiennent la collection `network_nodes`.
    """
    valid = []
    for name in client.list_database_names():
        try:
            if "network_nodes" in client[name].list_collection_names():
                valid.append(name)
        except errors.PyMongoError:
            continue
    return valid


# def match_company(input_name: str) -> str | None:
#     """
#     Tente de faire correspondre `input_name` avec la liste des bases disponibles.

#     1) Exact match sur slug (normalisation de casse, espaces, underscores).
#     2) Sinon fuzzy match sur ces mêmes slugs (cutoff=0.6).

#     Renvoie le nom exact de la base, ou None si aucun match.
#     """
#     companies = list_companies()

#     # Construire un mapping slug → vrai nom de base
#     slug_map: dict[str, str] = {}
#     for name in companies:
#         # slug sur le nom brut
#         slug_map[slugify_company(name)] = name
#         # slug sur le nom avec "_" remplacé par un espace
#         alt = name.replace("_", " ")
#         slug_map[slugify_company(alt)] = name

#     # Slugifier la saisie utilisateur
#     probe = slugify_company(input_name)

#     # 1) Exact match sur slug
#     if probe in slug_map:
#         return slug_map[probe]

#     # 2) Fuzzy match sur les clés du mapping
#     close = difflib.get_close_matches(probe, list(slug_map.keys()), n=1, cutoff=0.6)
#     return slug_map[close[0]] if close else None

def find_company_candidates(input_name: str) -> list[str]:
    companies = list_companies()
    print(f"[DEBUG] companies list: {companies}")

    slug_map: dict[str,str] = {}
    for name in companies:
        slug_map[slugify_company(name)] = name
        slug_map[slugify_company(name.replace("_", " "))] = name
    print(f"[DEBUG] slug_map keys: {list(slug_map.keys())}")

    probe = slugify_company(input_name)
    print(f"[DEBUG] input_name='{input_name}' → probe='{probe}'")

    # 1) Exact
    if probe in slug_map:
        print(f"[DEBUG] exact match on '{probe}' → {slug_map[probe]}")
        return [slug_map[probe]]

    # 2) Préfixe
    prefix_matches = [slug_map[s] for s in slug_map if s.startswith(probe) and probe]
    print(f"[DEBUG] prefix_matches for '{probe}': {prefix_matches}")
    if prefix_matches:
        unique = list(dict.fromkeys(prefix_matches))
        print(f"[DEBUG] returning prefix unique: {unique}")
        return unique
    
     # 3) Sous-chaîne  ← NOUVEAU
    substr = [slug_map[s] for s in slug_map if s in probe]
    if substr:
        chaine = list(dict.fromkeys(substr))
        print(f"[DEBUG] returning chaine : {chaine}")
        return chaine

    # 4) Fuzzy
    close = difflib.get_close_matches(probe, list(slug_map.keys()),
                                      n=len(slug_map), cutoff=0.6)
    result = list({slug_map[s] for s in close})
    print(f"[DEBUG] fuzzy close matches: {close} → {result}")
    return result

def get_default_db(client_id: str):
    # Retourne le nom de DB correspondant au client
    return client_id

def execute_db_query(
    client_id: str,
    collection: str,
    filter: Dict[str, Any] | None = None,
    projection: Dict[str, int] | None = None,
    limit: Optional[int] = None
) -> List[Dict[str, Any]]:

    print(
        f"[DB] query → db='{client_id}', coll='{collection}', "
        f"filter={json.dumps(filter, ensure_ascii=False)}",
        flush=True
    )

    col = client[client_id][collection]
    cursor = col.find(filter or {}, projection or None)
    if limit is not None:          # ⇦ n’ajoute .limit() que si un entier est fourni
        cursor = cursor.limit(limit)
    return list(cursor)

def describe_schema(
    client_id: str,
    collection: str,
) -> List[str]:
    """
    Liste dynamiquement les clés de la collection.
    Utile pour guider le LLM.
    """
    db = client[get_default_db(client_id)]
    # Liste des champs par récupération d’un sample
    sample = db[collection].find_one({}) or {}
    return list(sample.keys())