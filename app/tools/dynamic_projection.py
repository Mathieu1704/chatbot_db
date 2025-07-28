"""
Projection dynamique ZÉRO champ codé en dur
• Profil d’échantillon basé sur utils.serialize.flatten_doc
• Logs : prompt, profil (5 premiers), réponse brute, projection finale
"""

from __future__ import annotations
import os, json, hashlib, asyncio, datetime, re, pprint
from typing import List, Dict, Any
from time import perf_counter
from concurrent.futures import ThreadPoolExecutor

from cachetools import TTLCache
from openai import AsyncOpenAI
from bson import ObjectId

from app.db import client
from app.utils.serialize import flatten_doc   # ← ré-utilise ton helper

# ---------------------------------------------------------------------------
# Paramètres
# ---------------------------------------------------------------------------
_LLM     = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
_CACHE   = TTLCache(maxsize=10_000, ttl=24 * 3600)

N_SAMPLE = int(os.getenv("DYN_PROJ_SAMPLE_SIZE", "50"))
MAX_FLD  = int(os.getenv("DYN_PROJ_MAX_FIELDS", "60"))
MAX_RETN = int(os.getenv("DYN_PROJ_MAX_RETURN", "12"))
FALLBACK = int(os.getenv("DYN_PROJ_FALLBACK",    "15"))

# ---------------------------------------------------------------------------
# Helpers simples
# ---------------------------------------------------------------------------
def _hash(txt: str) -> str:
    return hashlib.sha1(txt.encode()).hexdigest()

def _dtype(val: Any) -> str:
    if isinstance(val, (int, float)):           return "number"
    if isinstance(val, datetime.datetime):      return "date"
    if isinstance(val, str):
        return "date" if re.match(r"\d{4}-\d{2}-\d{2}", val) else "string"
    if isinstance(val, list):                   return "array"
    if isinstance(val, ObjectId):               return "id"
    return "object"

_digit_re = re.compile(r"^\d+$")

def _normalize_sentence_path(path: str) -> str:
    """
    Supprime les segments numériques intermédiaires :
      analyses.0.description.1.sentence  ->  analyses.description.sentence
    """
    parts = [p for p in path.split(".") if not _digit_re.match(p)]
    return ".".join(parts)

def _collect_sentence_paths(obj, prefix="", out=None):
    """
    Parcourt récursivement `obj` (dict ou list) et enregistre tous les
    chemins qui se terminent par '.sentence', sans indices numériques.
    """
    if out is None:
        out = set()

    if isinstance(obj, dict):
        for k, v in obj.items():
            new_pref = f"{prefix}.{k}" if prefix else k
            if k == "sentence":
                out.add(_normalize_sentence_path(new_pref))       
            else:
                _collect_sentence_paths(v, new_pref, out)

    elif isinstance(obj, list):
        for item in obj:
            _collect_sentence_paths(item, prefix, out)

    return out



# ---------------------------------------------------------------------------
# Profilage d’une collection
# ---------------------------------------------------------------------------
def _sample_profile(db: str, coll: str) -> List[Dict[str, Any]]:
    docs   = list(client[db][coll].aggregate([{"$sample": {"size": N_SAMPLE}}]))
    total  = len(docs) or 1
    stats: Dict[str, list[Any]] = {}

    for raw in docs:
        flat = flatten_doc(raw, sep=".")           # ← SEP = "."
        for k, v in flat.items():
            stats.setdefault(k, []).append(v)

        for path in _collect_sentence_paths(raw):
            stats.setdefault(path, []).append("•")

    prof = [{
        "name":   k,
        "type":   _dtype(vals[0]),
        "freq":   round(len(vals) * 100 / total),
        "sample": str(vals[0])[:60]
    } for k, vals in stats.items()]

    prof.sort(key=lambda d: (-d["freq"], d["name"]))
    return prof[:MAX_FLD]

def _merge_profiles(all_prof: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    freq, typ, samp = {}, {}, {}
    for prof in all_prof:
        for d in prof:
            n = d["name"]
            freq[n] = max(freq.get(n, 0), d["freq"])
            typ.setdefault(n, d["type"])
            samp.setdefault(n, d["sample"])

    merged = [{"name": n, "type": typ[n], "freq": freq[n], "sample": samp[n]}
              for n in freq]
    merged.sort(key=lambda d: (-d["freq"], d["name"]))
    return merged[:MAX_FLD]

def _make_sentence_extractor(path_parts: list[str]) -> dict:
    """
    Pour un chemin ['analyses','recommendations','sentence'] ou plus long,
    renvoie soit un $map simple (len=2) soit un $reduce qui concatène les maps.
    """
    # cas de base : root.sentence
    if len(path_parts) == 2:
        root = path_parts[0]
        return {
            "$map": {
                "input": f"${root}",
                "as": "e",
                "in": "$$e.sentence"
            }
        }

    # cas récursif : on produit un reduce sur le premier niveau,
    # et on injecte le sous-extracteur sur les parties suivantes
    root = path_parts[0]
    rest = path_parts[1:]
    return {
        "$reduce": {
            "input": f"${root}",
            "initialValue": [],
            "in": {
                "$concatArrays": [
                    "$$value",
                    # ici on veut extraire les sentences de $$this.<rest>
                    _make_inner_extractor(rest)
                ]
            }
        }
    }

def _make_inner_extractor(path_parts: list[str]) -> dict:
    """
    Similaire à _make_sentence_extractor, mais on part de $$this au lieu de $.
    Permet de descendre les niveaux imbriqués.
    """
    # ['recommendations','sentence']
    if len(path_parts) == 2:
        arr_field = path_parts[0]
        return {
            "$map": {
                "input": f"$$this.{arr_field}",
                "as": "e",
                "in": "$$e.sentence"
            }
        }

    # plus de deux niveaux : on fait un reduce sur $$this.<first>
    first = path_parts[0]
    rest = path_parts[1:]
    return {
        "$reduce": {
            "input": f"$$this.{first}",
            "initialValue": [],
            "in": {
                "$concatArrays": [
                    "$$value",
                    _make_inner_extractor(rest)
                ]
            }
        }
    }


# ---------------------------------------------------------------------------
# JSON-SCHEMA (minProperties + schéma simple)
# ---------------------------------------------------------------------------
JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "projection": {
            "type": "object",
            "minProperties": 2,
            "maxProperties": MAX_RETN,
            "additionalProperties": {
                "type": "integer",
                "enum": [1]
            }
        }
    },
    "required": ["projection"]
}

# ---------------------------------------------------------------------------
# Build aggregation pipeline from projection dict
# ---------------------------------------------------------------------------
def build_agg_pipeline(match_filter: dict, proj: Dict[str,int]) -> List[dict]:
    """
    Transforme le dict de projection plat en pipeline d’agrégation
    - garde tous les champs scalaires
    - pour chaque clé en dot-notation finissant par '.sentence',
      génère un array de toutes les phrases (quel que soit le niveau d’imbrication)
    - s’assure que 'asset' est toujours projeté
    """
    pipeline: List[dict] = []
    if match_filter:
        pipeline.append({"$match": match_filter})

    # 1) On force la présence du champ asset
    proj.setdefault("asset", 1)

    proj_stage: Dict[str, Any] = {}
    for key, include in proj.items():
        # Si c'est un champ .sentence à toute profondeur
        if key.endswith(".sentence"):
            parts = key.split(".")
            out_field = "_".join(parts[:-1]) + "_sentences"
            proj_stage[out_field] = _make_sentence_extractor(parts)
        else:
            # Tout le reste : projection simple
            proj_stage[key] = f"${key}"

    pipeline.append({"$project": proj_stage})
    return pipeline


# ---------------------------------------------------------------------------
# Appel LLM
# ---------------------------------------------------------------------------
async def _ask_llm(profile: list[dict], question: str) -> Dict[str, int]:
    sys = """
        SYSTEM
        Tu es Data Architect chez I-CARE.
        Sélectionne les champs les PLUS UTILES (≤ 12) pour un tableau
        de maintenance prédictive.

        Règles :

        1. Privilégie les SCALAIRES (string, number, date).
        Si un champ est un objet/array, préfère une de ses sous-clés métier
        (ex. analyses.failure.name) plutôt que l’objet entier.

        2. Pour EXTRAIRE des phrases depuis un tableau d’objets {sentence:…},
        utilise toujours la notation par points :
        • explanation.sentence  
        • analyses.recommendations.sentence  

        3. Si l’utilisateur mentionne un champ spécifique (par ex. “rssi”),
        ajoute-le systématiquement si ce champ est présent dans les documents.

        4. Renvoie TOUJOURS le champ "asset" dans les projections/aggrégations.

        5. Classement par utilité :
        • asset
        • action/explication (explanation.sentence, analyses.recommendations.sentence)  
        • techno (technology.name)  
        • sévérité (status.name, status.level)  
        • dates (measured_date, planned_date, deadline)  
        • auteur (agent.email)

        6. Évite : _etag, _created, chemins média, les champs optionals, coordonnées GPS brutes.

        Réponds STRICTEMENT via la function **select** :

        { "projection": { "champ1": 1, … } }

        Exemple valide :
        { "projection": {
        "asset": 1,
        "technology.name": 1,
        "status.name": 1,
        "status.level": 1,
        "planned_date": 1,
        "explanation.sentence": 1,
        "analyses.recommendations.sentence": 1,
        "rssi": 1
        }}
        (minProperties ≥ 2)

    """
    usr = json.dumps({"question": question, "fields": profile}, ensure_ascii=False)

    def _call(temp: float):
        return _LLM.chat.completions.create(
            model="gpt-4o-mini",
            temperature=temp,
            messages=[{"role": "system", "content": sys},
                      {"role": "user",   "content": usr}],
            functions=[{"name": "select", "parameters": JSON_SCHEMA}],
            function_call={"name": "select"},
            timeout=25
        )

    resp = None
    try:
        resp = await _call(0.25)
    except Exception as e:
        print("[LLM-ERROR 1]", e)
    raw = {}
    if resp:
        fc = resp.choices[0].message.function_call
        print("[LLM-FUNC RAW]", fc)
        try:
            raw = json.loads(fc.arguments).get("projection", {})
        except:
            pass

    if not raw:
        print("[LLM] retry temp 0.6")
        try:
            resp2 = await _call(0.6)
            fc2   = resp2.choices[0].message.function_call
            print("[LLM-FUNC RAW 2]", fc2)
            raw = json.loads(fc2.arguments).get("projection", {}) or {}
        except Exception as e:
            print("[LLM-ERROR 2]", e)

    return {k:1 for k,v in raw.items() if v==1}

# ---------------------------------------------------------------------------
# Mono-DB
# ---------------------------------------------------------------------------
async def build_dynamic_projection(
    client_id: str,
    collection: str,
    user_query: str,
    match_filter: dict = None
) -> List[dict]:
    """
    Retourne la liste de documents projetés via aggregation,
    avec extraction des champs .sentence en tableaux de phrases.
    """
    t0      = perf_counter()
    profile = _sample_profile(client_id, collection)
    cache_k = _hash(user_query + _hash(json.dumps(profile, sort_keys=True)))

    if cache_k in _CACHE:
        print(f"[DYN] cache-hit {cache_k[:8]}")
        return _CACHE[cache_k]

    proj = await _ask_llm(profile, user_query)
    if not proj:
        proj = {d["name"]:1 for d in profile[:FALLBACK]}
        print(f"[DYN] fallback ({len(proj)} champs)")

    # On s'assure d'inclure TOUTES les clés se terminant par '.sentence'
    # repérées dans le profil, même si le LLM ne les a pas listées.
    for fld in (d["name"] for d in profile):
        if fld.endswith(".sentence"):
            proj.setdefault(fld, 1)

    pipeline = build_agg_pipeline(match_filter or {}, proj)
    docs     = list(client[client_id][collection].aggregate(pipeline))

    dur = int((perf_counter() - t0)*1000)
    print(f"[DYN] agg_pipeline {pipeline}")
    print(f"[DYN] result {len(docs)} docs in {dur}ms")

    _CACHE[cache_k] = docs
    return docs

# ---------------------------------------------------------------------------
# Cross-DB (similaire au mono-DB, on merge profils puis pipeline)
# ---------------------------------------------------------------------------
async def build_dynamic_projection_multi(
    client_ids: List[str],
    collection: str,
    user_query: str,
    match_filter: dict = None
) -> List[dict]:
    t0 = perf_counter()                         # ← pour le chrono
    
    # 1) Profil fusionné
    profile = _merge_profiles([
        _sample_profile(db, collection) for db in client_ids
    ])
    cache_k = _hash(user_query + _hash(json.dumps(profile, sort_keys=True)))

    # -- A) Early-cache (comme en mono-DB) -------------------------------
    if cache_k in _CACHE:
        print(f"[DYN-M] cache-hit {cache_k[:8]}")
        return _CACHE[cache_k]
    # -------------------------------------------------------------------

    # 2) Projection choisie par le LLM
    proj = await _ask_llm(profile, user_query)
    if not proj:
        proj = {d["name"]: 1 for d in profile[:FALLBACK]}
        print(f"[DYN-M] fallback ({len(proj)} champs)")

    # -- B) Injection de TOUTES les clés *.sentence ----------------------
    for fld in (d["name"] for d in profile):
        if fld.endswith(".sentence"):
            proj.setdefault(fld, 1)
    # -------------------------------------------------------------------

    # 3) Exécution parallèle sur chaque base
    all_docs: List[dict] = []
    for cid in client_ids:
        pipeline = build_agg_pipeline(match_filter or {}, proj)
        docs = list(client[cid][collection].aggregate(pipeline))
        for d in docs:
            d["_company"] = cid
        all_docs.extend(docs)

    # 4) Cache + retour
    _CACHE[cache_k] = all_docs

    dur = int((perf_counter() - t0) * 1000)      # ← petit log optionnel
    print(f"[DYN-M] result {len(all_docs)} docs in {dur}ms")

    return all_docs
