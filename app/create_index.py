from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()
client = MongoClient(os.getenv("MONGODB_URI"))
db     = client[os.getenv("DB_NAME")]
nodes  = db["network_nodes"]

# Création de l’index
nodes.create_index(
    [("node_type", 1), ("last_com", 1)],
    name="idx_nodeType_lastCom",
    background=True
)
print("Index créé.")
