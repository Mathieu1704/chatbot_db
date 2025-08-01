from typing import Any, Dict, List

# Intention(s) en attente (ex. collecte d'un paramètre manquant)
PENDING: Dict[str, Dict[str, Any]] = {}

# Historique complet des messages par session (fin à fin)
# Chaque message est un dict {role: str, content: str, ...}
CONVERSATIONS: Dict[str, List[Dict[str, Any]]] = {}
