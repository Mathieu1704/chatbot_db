from bson import ObjectId
from datetime import datetime, date

def serialize_docs(docs):
    """Convertit ObjectId & datetime en str pour la réponse JSON."""
    out = []
    for d in docs:
        clean = {}
        for k, v in d.items():
            if isinstance(v, ObjectId):
                clean[k] = str(v)
            elif isinstance(v, (datetime, date)):
                clean[k] = v.isoformat()
            else:
                clean[k] = v
        out.append(clean)
    return out
