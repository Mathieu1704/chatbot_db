#!/usr/bin/env python3
# coding: utf-8

import os
import json
from pymongo import MongoClient, UpdateOne
from sentence_transformers import SentenceTransformer
from tqdm.auto import tqdm
from dotenv import load_dotenv
# ---------------------------------------------------
# 1) Configuration & connexion
# ---------------------------------------------------
# Variables d'environnement attendues :
#   MONGO_URI : votre URI de connexion MongoDB
#   BATCH_SIZE: nombre de docs par batch d'encoding (p.ex. 512)
# Exemple export MONGO_URI="mongodb+srv://user:pass@cluster0.mongodb.net"
load_dotenv()
MONGO_URI   = os.getenv("MONGODB_URI")
BATCH_SIZE  = int(os.getenv("BATCH_SIZE", "512"))

if not MONGO_URI:
    raise RuntimeError("Il faut définir la variable MONGO_URI")

client = MongoClient(MONGO_URI)
print(f"[INFO] Connecté à MongoDB Atlas : {MONGO_URI}")

# ---------------------------------------------------
# 2) Charger le modèle d'embeddings sur GPU
# ---------------------------------------------------
# Vous pouvez choisir un autre modèle si besoin
MODEL_NAME = "all-MiniLM-L6-v2"
print(f"[INFO] Chargement du modèle '{MODEL_NAME}' sur GPU...")
model = SentenceTransformer(MODEL_NAME, device="cuda")

# ---------------------------------------------------
# 3) Fonctions utilitaires
# ---------------------------------------------------
def list_dbs_with_network_nodes():
    """
    Retourne la liste des noms de bases qui contiennent la collection 'network_nodes'.
    """
    result = []
    for db_name in client.list_database_names():
        try:
            cols = client[db_name].list_collection_names()
            if "network_nodes" in cols:
                result.append(db_name)
        except Exception:
            continue
    return result
    print(f"[INFO] Bases trouvées avec 'network_nodes' : {result}")

def stream_batches(db_name, coll_name, batch_size=BATCH_SIZE):
    """
    Génère des tuples ([_id,...], [blob_text,...]) par batch
    - On ne charge que le champ _id + les champs textuels pertinents
    - L'ordre d'insertion est préservé
    """
    coll = client[db_name][coll_name]
    cursor = coll.find(
        {}, 
        projection={"_id":1, "address":1, "parent":1, "network_partition_id":1, "parents":1, "node_type":1, "net_type":1}
    )
    batch_ids, batch_blobs = [], []
    for doc in cursor:
        # 1) Construire le blob texte
        parts = [
            f"Address:{doc.get('address')}",
            f"Partition:{doc.get('network_partition_id')}",
            f"Parent:{doc.get('parent')}",
            f"Parents:" + ",".join(
                f"{p.get('address')}|type{p.get('node_type')}" for p in doc.get("parents",[])
            ),
            f"NodeType:{doc.get('node_type')}",
            f"NetType:{doc.get('net_type')}"
        ]
        blob = " ; ".join(parts)
        # 2) Stocker
        batch_ids.append(doc["_id"])
        batch_blobs.append(blob)
        if len(batch_ids) >= batch_size:
            yield batch_ids, batch_blobs
            batch_ids, batch_blobs = [], []
    # dernier batch éventuel
    if batch_ids:
        yield batch_ids, batch_blobs

# ---------------------------------------------------
# 4) Boucle principale d'indexation
# ---------------------------------------------------
def build_embeddings_all():
    dbs = list_dbs_with_network_nodes()
    print(f"[INFO] Bases trouvées avec 'network_nodes' : {dbs}")
    for db_name in dbs:
        coll_name = "network_nodes"
        coll = client[db_name][coll_name]
        print(f"\n[INFO] Traitement de {db_name}.{coll_name} ...")
        total = coll.count_documents({})
        print(f"[INFO]  → {total} documents trouvés")

        # Itérer par batch, encoder, et bulk_write
        pbar = tqdm(stream_batches(db_name, coll_name), total=(total // BATCH_SIZE) + 1)
        for batch_ids, batch_blobs in pbar:
            # 1) Générer les embeddings (shape: [len(batch), dim])
            embs = model.encode(batch_blobs, batch_size=len(batch_blobs), show_progress_bar=False)
            # 2) Préparer les opérations bulk
            ops = []
            for _id, emb in zip(batch_ids, embs):
                ops.append(
                    UpdateOne(
                        {"_id": _id},
                        {"$set": {"embedding": emb.tolist()}}
                    )
                )
            # 3) Exécuter
            result = coll.bulk_write(ops, ordered=False)
            pbar.set_postfix({
                "upserts": result.upserted_count,
                "mods":    result.modified_count
            })
        print(f"[DONE] Embeddings stockés pour {db_name}.{coll_name}")

if __name__ == "__main__":
    build_embeddings_all()
