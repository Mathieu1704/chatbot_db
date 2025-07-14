from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from app.db import get_nodes_collection

# seuil hors-ligne configurable (jours)
OFFLINE_DAYS = 2

# Montre test : on positionne "maintenant" au 3 juillet 2025
TEST_BASE_DATE = datetime(2025, 7, 3, tzinfo=timezone.utc)


def _offline_threshold() -> datetime:
    """
    Retourne le seuil pour considérer un capteur hors-ligne.
    On part de TEST_BASE_DATE pour simuler le 3 juillet 2025,
    on retire OFFLINE_DAYS jours, puis on ramène à minuit UTC.
    """
    # Calcul du seuil de déconnexion
    base = TEST_BASE_DATE
    # Retrait des jours configurés
    thresh = base - timedelta(days=OFFLINE_DAYS)
    # Ramener à minuit UTC
    return thresh.replace(hour=0, minute=0, second=0, microsecond=0)


def connectivity_overview(company: str) -> Dict[str, Any]:
    """
    Retourne l’état global des capteurs :

      connected_count      : nombre de capteurs en ligne
      disconnected_count   : nombre de capteurs hors-ligne
      total                : total capteurs (node_type = 2)
      items                : capteurs hors-ligne (jusqu’à 10 000) avec
                             address, batt, parent, rssi, last_com
    """
    seuil = _offline_threshold()
    filt  = {"node_type": 2}

    nodes = get_nodes_collection(company)

    connected     = nodes.count_documents({**filt, "last_com": {"$gte": seuil}})
    disconnected  = nodes.count_documents({**filt, "last_com": {"$lt":  seuil}})
    total         = connected + disconnected

    # Projection : on ajoute last_com
    proj = {
        "_id": 0,
        "address": 1,
        "batt": 1,
        "parent": 1,
        "rssi": 1,
        "last_com": 1,
    }

    items = (
        nodes.find({**filt, "last_com": {"$lt": seuil}}, proj)
             .sort("last_com", 1)
             .limit(10_000)
    )
    items = list(items)

    return {
        "connected_count": connected,
        "disconnected_count": disconnected,
        "total": total,
        "items": items
    }

# --- Nouvelle fonction battery_overview ---
DEFAULT_SAMPLE_SIZE = 10

def battery_overview(
    company: str,
    critical_threshold: int,
    warning_threshold: int,
    sample_size: int = DEFAULT_SAMPLE_SIZE
) -> Dict[str, Any]:
    """
    Retourne l'état des batteries pour l'entreprise `company` :
      - critical : batt < critical_threshold
      - warning  : critical_threshold <= batt < warning_threshold
      - ok       : batt >= warning_threshold

    Renvoie :
      {
        "counts": {"critical": X, "warning": Y, "ok": Z},
        "items_critical": [...],
        "items_warning": [...],
        "items_ok": [...]
      }
    """
    print(f"[DEBUG] battery_overview thresholds → critical={critical_threshold}, warning={warning_threshold}")
    nodes = get_nodes_collection(company)
    base_filter = {"node_type": 2}

    # Comptages
    crit_count = nodes.count_documents({
        **base_filter, "batt": {"$lt": critical_threshold}
    })
    warn_count = nodes.count_documents({
        **base_filter,
        "batt": {"$gte": critical_threshold, "$lt": warning_threshold}
    })
    ok_count = nodes.count_documents({
        **base_filter, "batt": {"$gte": warning_threshold}
    })
    print(f"[DEBUG] counts → critical={crit_count}, warning={warn_count}, ok={ok_count}")

    # Projection
    proj = {"_id": 0, "address": 1, "batt": 1, "parent": 1, "rssi": 1}

    # Échantillons triés
    items_critical = list(
        nodes.find({**base_filter, "batt": {"$lt": critical_threshold}}, proj)
             .sort("batt", 1)
             .limit(sample_size)
    )
    items_warning = list(
        nodes.find({
            **base_filter,
            "batt": {"$gte": critical_threshold, "$lt": warning_threshold}
        }, proj)
        .sort("batt", 1)
        .limit(sample_size)
    )
    items_ok = list(
        nodes.find({**base_filter, "batt": {"$gte": warning_threshold}}, proj)
             .sort("batt", -1)
             .limit(sample_size)
    )

    return {
        "counts": {"critical": crit_count, "warning": warn_count, "ok": ok_count},
        "items_critical": items_critical,
        "items_warning": items_warning,
        "items_ok": items_ok
    }



def battery_list(
    company: str,
    category: str,  # "critical", "warning" ou "ok"
    critical_threshold: int,
    warning_threshold: int,
) -> dict:
    """
    Retourne la liste des addresses pour la catégorie demandée.
    """
    # On appelle l’overview pour récupérer toutes les listes
    overview = battery_overview(company, critical_threshold, warning_threshold)
    mapping = {
        "critical": overview["items_critical"],
        "warning":  overview["items_warning"],
        "ok":       overview["items_ok"],
    }
    items = mapping.get(category.lower(), [])
    return {"category": category, "addresses": [d["address"] for d in items]}
