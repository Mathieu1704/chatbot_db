# utils/serialize.py
import json
from bson import ObjectId
from datetime import datetime, date

def _deep_clean(obj):
    """
    Nettoie récursivement :
      • supprime toutes les clés '_id' dans les dicts,
      • convertit ObjectId -> str,
      • convertit datetime/date -> ISO 8601,
      • traite listes et dicts.
    """
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, list):
        return [_deep_clean(item) for item in obj]
    if isinstance(obj, dict):
        return {
            k: _deep_clean(v)
            for k, v in obj.items()
            if k != "_id"
        }
    return obj

def flatten_doc(d: dict, parent_key: str = "", sep: str = "_") -> dict:
    """
    Aplatissement :
      - dict imbriqués -> clés concatenées parent_sep_child,
      - liste de scalaires -> "a, b, c",
      - listes/dicts complexes -> JSON compact (après deep_clean),
      - primitives -> deep_clean.
    """
    out = {}
    for k, v in d.items():
        if k == "_id":
            continue

        new_key = f"{parent_key}{sep}{k}" if parent_key else k

        # Nettoyage initial
        if isinstance(v, (ObjectId, datetime, date)):
            v = _deep_clean(v)

        if isinstance(v, dict):
            out.update(flatten_doc(v, new_key, sep))
        elif isinstance(v, list):
            # liste de scalaires purs ?
            if all(not isinstance(x, (dict, list, ObjectId, datetime, date)) for x in v):
                out[new_key] = ", ".join(str(x) for x in v)
            else:
                cleaned = _deep_clean(v)
                out[new_key] = json.dumps(cleaned, ensure_ascii=False, separators=(",", ":"))
        else:
            out[new_key] = v

    return out

def serialize_docs(docs):
    """
    Retourne la liste des docs Mongo « plats » et JSON-safe.
    """
    return [flatten_doc(doc) for doc in docs]
def clean_jsonable(obj):
    """Convertit récursivement ObjectId, datetime, etc. en types JSON-safe."""
    if isinstance(obj, list):
        return [clean_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: clean_jsonable(v) for k, v in obj.items()}
    # ↓ conversions de base
    from bson import ObjectId
    from datetime import datetime, date
    if isinstance(obj, (ObjectId, datetime, date)):
        return str(obj)
    return obj


def extract_columns(docs):
    """
    Union ordonnée des clés de tous les docs.
    """
    if not docs:
        return []
    seen, order = set(), []
    for doc in docs:
        for k in doc:
            if k not in seen:
                seen.add(k)
                order.append(k)
    # optionnel : placer _company en tête
    if "_company" in order:
        order.remove("_company")
        order.insert(0, "_company")
    return order
