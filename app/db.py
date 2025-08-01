import os
import json
import logging 
from bson.errors import InvalidId
from bson import ObjectId
from functools import lru_cache
from itertools import chain
import hashlib
from dotenv import load_dotenv
from pymongo import MongoClient, errors
from app.utils.slugify_company import slugify_company
from typing import Optional, Dict, Any, List
import difflib
from concurrent.futures import ThreadPoolExecutor, as_completed

# Charger .env
load_dotenv()

# Puis, juste :
MONGODB_URI = os.getenv("MONGODB_URI")
client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10_000)

try:
    client.admin.command("ping")
    print(f"[INFO] MongoDB reachable")
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

    # Si aucun slug n’est disponible (aucune DB network_nodes), on ne fuzzy-match pas
    if not slug_map:
        return []


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

def execute_cross_db_query(
    client_ids: list[str],
    collection: str,
    filter: Dict[str, Any] | None = None,
    projection: Dict[str, int] | None = None,
    limit: Optional[int] = None,
    max_workers: int = 10,
) -> List[Dict[str, Any]]:
    """
    Interroge plusieurs bases en parallèle et renvoie tous les documents,
    en ajoutant un champ '_company' à chaque doc pour indiquer sa source.
    """
    results: list[Dict[str, Any]] = []

    def worker(db_name: str) -> list[Dict[str, Any]]:
        # ne requête que si la collection existe dans la base
        if collection not in client[db_name].list_collection_names():
            return []
        docs = execute_db_query(
            client_id=db_name,
            collection=collection,
            filter=filter,
            projection=projection,
            limit=limit
        )
        for d in docs:
            d["_company"] = db_name
        return docs

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(worker, db): db for db in client_ids}
        for fut in as_completed(futures):
            results.extend(fut.result())

    return results


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

def _flatten(doc: dict, parent: str = "", sep: str = ".") -> dict:
    """Transforme un dict imbriqué en clés 'a.b.c'."""
    items = {}
    for k, v in doc.items():
        key = f"{parent}{sep}{k}" if parent else k
        if isinstance(v, dict):
            items.update(_flatten(v, key, sep))
        else:
            items[key] = v
    return items

def sample_fields(client_id: str, collection: str, size: int = 50) -> list[str]:
    """Union des clés d’un échantillon $sample."""
    pipe = [{"$sample": {"size": size}}]
    fields: set[str] = set()
    for doc in client[client_id][collection].aggregate(pipe):
        fields.update(_flatten(doc).keys())
    return sorted(fields)          # tri pour un fingerprint stable

def get_asset_by_id(client_id: str, asset_id: str) -> dict | None:
    """
    Retourne le document de la collection 'assets'
    pour l’ObjectId donné, dans la DB dont le nom correspond
    à client_id (insensible à la casse). 
    """
    # 1) Valider l’ObjectId
    try:
        oid = ObjectId(asset_id)
    except InvalidId as e:
        logging.error(f"get_asset_by_id: asset_id invalide « {asset_id} » – {e}")
        return None

    # 2) Trouver la DB en insensible à la casse
    db_name = next(
        (db for db in client.list_database_names() if db.lower() == client_id.lower()),
        None
    )
    if not db_name:
        logging.error(f"get_asset_by_id: DB introuvable – demandé « {client_id} »")
        return None
    db = client[db_name]

    # 3) Vérifier que la collection 'assets' existe
    if "assets" not in db.list_collection_names():
        logging.error(f"get_asset_by_id: collection 'assets' introuvable dans {db_name}")
        return None

    # 4) Récupérer le document
    try:
        return db["assets"].find_one({"_id": oid})
    except Exception as e:
        logging.exception(f"get_asset_by_id: erreur find_one sur {db_name}.assets pour {asset_id}")
        return None