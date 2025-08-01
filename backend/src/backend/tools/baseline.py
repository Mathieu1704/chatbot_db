# app/tools/baseline.py
#!/usr/bin/env python3
"""
Calcule, pour chaque capteur (asset),
le taux d’erreur nominal p₀ = erreurs / exécutions sur les X derniers jours,
et stocke le résultat dans la collection 'baseline_error_rate'.

Usage CLI :
    python app/tools/baseline.py --company MA_COMPAGNIE --days 30
"""

from datetime import datetime, timedelta
from backend.db import client

# ── Valeurs par défaut ───────────────────────────────────────
BASELINE_DAYS = 30

def compute_baseline(company: str, days: int = BASELINE_DAYS) -> None:
    db = client[company]
    cutoff = datetime.utcnow() - timedelta(days=days)

    pipeline = [
        # 1) on ne garde que les stats récentes ET avec un asset défini
        {"$match": {
            "asset":    {"$exists": True, "$ne": None},
            "acqend":   {"$gte": cutoff}
        }},
        # 2) agrégation par asset
        {"$group": {
            "_id": "$asset",
            "n":   {"$sum": 1},
            "k":   {"$sum": {
                "$cond": [
                    {"$gt": ["$log.errcode", 0]},
                    1,
                    0
                ]
            }}
        }},
        # 3) calcul du taux p0
        {"$project": {
            "_id":      1,
            "p0":       {"$cond": [
                            {"$gt": ["$n", 0]},
                            {"$divide": ["$k", "$n"]},
                            0
                        ]},
            "n":        1,
            "k":        1,
            "updated":  datetime.utcnow()
        }},
        # 4) upsert dans baseline_error_rate
        {"$merge": {
            "into":            "baseline_error_rate",
            "on":              "_id",
            "whenMatched":     "replace",
            "whenNotMatched":  "insert"
        }}
    ]

    db["statistics"].aggregate(pipeline, allowDiskUse=True)
    print(f"[{company}] baseline_error_rate mis à jour pour les {days} derniers jours")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Rebuild baseline_error_rate pour une compagnie donnée"
    )
    parser.add_argument(
        "--company", "-c",
        default="ACME",
        help="Nom de la DB Mongo / compagnie (défaut: ACME)"
    )
    parser.add_argument(
        "--days", "-d",
        type=int,
        default=BASELINE_DAYS,
        help=f"Période en jours pour le calcul du baseline (défaut: {BASELINE_DAYS})"
    )
    args = parser.parse_args()
    compute_baseline(args.company, days=args.days)
