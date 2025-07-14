#!/usr/bin/env python3
"""
Recherche vectorielle + filtres sur Atlas (M0 / MongoDB 7.x)
------------------------------------------------------------
• Génère un embedding OpenAI
• Interroge la collection network_nodes avec $vectorSearch
"""

import os
import json
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from pymongo import MongoClient
import openai

# ─────────────────────────────── 1) CONFIG ────────────────────────────────
load_dotenv()                                      # charge .env dans l’environnement
client = MongoClient(os.getenv("MONGODB_URI"))     # URI Atlas standard
openai.api_key = os.getenv("OPENAI_API_KEY")

DB_NAME        = "Icare_Brussels"
COLLECTION     = "network_nodes"
VECTOR_INDEX   = "vector_index"    # nom exact de l’index dans l’UI Atlas
K              = 200                 # top-k
NUM_CANDIDATES = 10000               # règle empirique ≈ 20–50 × k

# ───────────────────────────── 2) EMBEDDING ───────────────────────────────
query_text = "surchauffe"

resp = openai.embeddings.create(
    model="text-embedding-3-small",
    input=[query_text],
    dimensions=384           # même dimension que l’index
)
embedding = resp.data[0].embedding     # liste de floats (dim = 384)

# ──────────────────────── 3) PIPELINE VECTORSEARCH ───────────────────────
seuil = datetime.now(timezone.utc) - timedelta(days=2)   # date « aware »

pipeline = [
    {
        "$vectorSearch": {
            "index": VECTOR_INDEX,
            "path":  "embedding",
            "queryVector": embedding,
            "numCandidates": NUM_CANDIDATES,   # obligatoire en ANN
            "limit": K,                        # nombre de résultats
            "filter": {
                "last_com": {"$lt": seuil},
                "batt":     {"$lt": 3500}
            }
        }
    }
]

# ──────────────────────── 4) EXÉCUTION & AFFICHAGE ───────────────────────
db = client[DB_NAME]
results = list(db[COLLECTION].aggregate(pipeline))

print("\n── Résultats vectorSearch + filtres ──\n")
for doc in results:
    addr      = doc.get("address", "n/a")
    last_com  = doc.get("last_com")
    batt      = doc.get("batt")
    print(f"• {addr:20s}  last_com: {last_com}  batt: {batt}")

print(f"\n{len(results)} document(s) trouvé(s).\n")
