import os
import random
import string
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient
from dotenv import load_dotenv

# --- Configuration ------------------------------------------------
load_dotenv()
MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME      = os.getenv("DB_NAME", "Icare_Brussels")
COLLECTION    = "network_nodes"
NUM_NODES     = int(os.getenv("NUM_NETWORK_NODES", "10000"))
OFFLINE_COUNT = int(os.getenv("OFFLINE_COUNT", "150"))  # nombre fixe de noeuds offline
JOURS_SEUIL = int(os.getenv("JOURS_SEUIL", "2"))


# --- Helpers -------------------------------------------------------
def rand_mac() -> str:
    return ''.join(random.choices('0123456789ABCDEF', k=12))

def rand_id(prefix: str, length: int = 24) -> str:
    return prefix + ''.join(random.choices(string.hexdigits.lower(), k=length))

# --- Main seed logic -----------------------------------------------
def main():
    client = MongoClient(MONGODB_URI)
    db = client[DB_NAME]
    collection = db[COLLECTION]

    # clear old data
    collection.drop()
    print(f"Dropped existing '{COLLECTION}' collection")

    # Fixed "today" date for reproducibility
    now = datetime(2025, 7, 3, tzinfo=timezone.utc)
    threshold = (now - timedelta(days=JOURS_SEUIL)).replace(
        hour=0, minute=0, second=0, microsecond=0)  # seuil de "offline"

    docs = []
    # 1) Générer exactement OFFLINE_COUNT noeuds déconnectés (node_type=2)
    for _ in range(OFFLINE_COUNT):
        doc = {
            "_created": now,
            "_updated": now,
            "_etag": rand_id('e', 32),
            "address": rand_mac(),
            "batt": random.randint(3000, 4200),
            # Offline: last_com fixé au 30 juin 2025
            "last_com": threshold - timedelta(minutes=1),
            "net_type": 1,
            "network_partition_id": rand_id('p', 24),
            "node_type": 2,
            "parent": rand_mac(),
            "parents": [{"address": rand_mac(), "node_type": 1}],
            "rssi": random.randint(-100, -30)
        }
        docs.append(doc)

    # 2) Générer le reste en ligne (NUM_NODES - OFFLINE_COUNT)
    online_count = NUM_NODES - OFFLINE_COUNT
    online_seconds = int((now - threshold).total_seconds())
    for _ in range(online_count):
        # dans la boucle “online” :
        sec = random.randint(0, online_seconds)
        last_com = threshold + timedelta(seconds=sec)
        
        doc = {
            "_created": now,
            "_updated": now,
            "_etag": rand_id('e', 32),
            "address": rand_mac(),
            "batt": random.randint(1000, 4200),
            "last_com": last_com,
            "net_type": 1,
            "network_partition_id": rand_id('p', 24),
            "node_type": 2,
            "parent": rand_mac(),
            "parents": [{"address": rand_mac(), "node_type": 1}],
            "rssi": random.randint(-100, -30)
        }
        docs.append(doc)

    # Insert all docs
    collection.insert_many(docs)
    print(f"Inserted {len(docs)} fake network_nodes into '{COLLECTION}'")

if __name__ == "__main__":
    main()
