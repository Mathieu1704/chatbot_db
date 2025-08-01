#!/usr/bin/env python3
"""
create_indexes_roquette.py
──────────────────────────────────────────────────────────────────
Crée l’index composite indispensable à la détection des tasks
mal configurées dans la base MongoDB locale “roquette_local”.

• Se base sur la variable MONGODB_URI déjà définie dans .env
  (→ mongodb://localhost:27017/).
• Base par défaut : “roquette_local” (modifiable via la var. d’env DB_NAME).
• Idempotent : si l’index existe, il ne fait rien.
• Exécution en tâche de fond (background=True).

Usage :
    python create_indexes_roquette.py
"""

import os
from dotenv import load_dotenv
from pymongo import MongoClient, errors

# ── 1. Chargement .env ─────────────────────────────────────────────
load_dotenv()  # lit .env à la racine du projet
MONGODB_URI = os.getenv(
    "MONGODB_URI",
    "mongodb://localhost:27017/"        # défaut local
)
DB_NAME    = os.getenv(
    "DB_NAME",
    "test"                   # base où tu as restauré tes dumps
)
COLLECTION   = "statistics"
INDEX_NAME   = "idx_task_acqend"
INDEX_FIELDS = [("acqinfo.task", 1), ("acqend", -1)]

# ── 2. Création “create-if-not-exists” ─────────────────────────────
def main() -> None:
    try:
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5_000)
        # Ping pour valider la connexion
        client.admin.command("ping")
    except errors.PyMongoError as exc:
        print(f"❌ Impossible de joindre MongoDB à {MONGODB_URI} : {exc}")
        return

    col = client[DB_NAME][COLLECTION]

    # Vérifie si l’index existe déjà
    existing = [idx["name"] for idx in col.list_indexes()]
    if INDEX_NAME in existing:
        print(f"✅ Index « {INDEX_NAME} » déjà présent sur {DB_NAME}.{COLLECTION}")
        return

    # Création de l’index en tâche de fond
    print(f"➕ Création de l’index « {INDEX_NAME} » sur {DB_NAME}.{COLLECTION} …")
    col.create_index(
        INDEX_FIELDS,
        name=INDEX_NAME,
        background=True
    )
    print("✅ Index créé (build en arrière-plan).")

if __name__ == "__main__":
    main()
