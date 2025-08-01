# app/tools/misconfiguration.py
from datetime import datetime, timedelta
from typing import Any

from backend.db import client
from backend.utils.serialize import flatten_doc
from backend.utils.error_meta import load_err_meta

# ── Métadonnées erreurs ──────────────────────────────────────
ERR_META     = load_err_meta()                         # clé décimale → dict
ERR_META_STR = {str(k): v for k, v in ERR_META.items()}


def detect_misconfig(
    company: str,
    since_days: int = 30,
    last_n: int = 10,
    freq_threshold: int = 3,
) -> dict[str, Any]:
    """
    Pour chaque asset (capteur) :
     - Récupère les `last_n` statistiques récentes (acqend >= cutoff)
     - Calcule freq_err, last_errcode, consec_errs, is_immediate selon severity
     - Détermine misconfiguration si :
         * R1′ : sévérité Critical (immediate) ou 2 erreurs consécutives
         * R2  : freq_err >= freq_threshold
    Retourne counts, liste d’assets KO avec détails et agrégats par transmitter.
    """
    db     = client[company]
    cutoff = datetime.utcnow() - timedelta(days=since_days)

    assets = client[company]["assets"]
    # ── Comptage de TOUS les MP par transmitter ───────────────────────────
    raw_totals = list(assets.aggregate([
        {"$match": {"optionals.transmitter": {"$exists": True}}},

        # a) 2 représentations de l’id : objet + chaîne
        {"$addFields": {
            # tentative de conversion → ObjectId ; null si impossible
            "txObj": {
                "$convert": {
                    "input": "$optionals.transmitter",
                    "to": "objectId",
                    "onError": "optionals.transmitter",
                    "onNull":  None
                }
            },
            # représentation texte uniforme pour le regroupement
            "txKey": {
                "$cond": [
                    { "$eq": [{ "$type": "$optionals.transmitter" }, "objectId"] },
                    { "$toString": "$optionals.transmitter" },
                    "$optionals.transmitter"
                ]
            }
        }},

        # b) groupement sur la clé texte → on ne rate jamais un asset
        {"$group": {
            "_id":      "$txKey",
            "totalMP":  { "$sum": 1 }
        }}
    ]))
    # → map: { "63bb…07e": 5, … }
    total_map = { d["_id"]: d["totalMP"] for d in raw_totals }


    pipeline = [
        # 1) lookup des last_n stats PAR asset
        {
            "$lookup": {
                "from": "statistics",
                "let": {"assetId": "$asset"},
                "pipeline": [
                    {"$match": {
                        "$expr": {"$eq": ["$asset", "$$assetId"]},
                        "acqend": {"$gte": cutoff}
                    }},
                    {"$sort": {"acqend": -1}},
                    {"$limit": last_n},
                ],
                "as": "lastStats"
            }
        },
        # 2) ne garder que les assets avec au moins 1 stat
        {"$match": {"lastStats.0": {"$exists": True}}},

        # 3) extraire errcodes et freq_err + last_errcode
        {"$addFields": {
            "errcodes": {
                "$map": {
                    "input": "$lastStats",
                    "as": "st",
                    "in": {"$ifNull": ["$$st.log.errcode", 0]}
                }
            }
        }},
        {"$addFields": {
            "freq_err":   {"$size": {"$filter": {"input": "$errcodes", "as": "e", "cond": {"$gt": ["$$e", 0]}}}},
            "last_errcode": {"$arrayElemAt": ["$errcodes", 0]}
        }},

        # 4) séquence d’erreurs consécutives
        {"$addFields": {
            "consec_count": {
                "$reduce": {
                    "input": "$errcodes",
                    "initialValue": {"count": 0, "stop": False},
                    "in": {
                        "$cond": [
                            {"$or": [
                                {"$eq": ["$$value.stop", True]},
                                {"$eq": ["$$this", 0]}
                            ]},
                            {"count": "$$value.count", "stop": True},
                            {"count": {"$add": ["$$value.count", 1]}, "stop": False}
                        ]
                    }
                }
            }
        }},

        # 5) règles R1′ + R2
        {"$addFields": {
            "is_immediate": {
                "$eq": [
                    {"$function": {
                        "lang": "js",
                        "args": ["$last_errcode", ERR_META_STR],
                        "body": "function(c,m){return m[String(c)]?m[String(c)].severity:'Unknown';}"
                    }},
                    "Critical"
                ]
            },
            "consec_errs": {
                "$and": [
                    {"$gt": [{"$arrayElemAt": ["$errcodes", 0]}, 0]},
                    {"$gt": [{"$arrayElemAt": ["$errcodes", 1]}, 0]}
                ]
            }
        }},
        {"$addFields": {
            "misconfigured": {
                "$or": [
                    "$is_immediate",
                    "$consec_errs",
                    {"$gte": ["$consec_count.count", freq_threshold]}
                ]
            }
        }},

        # 6) ENRICHISSEMENT COMMUN À TOUTES LES FACETS
        {"$lookup": {
            "from": "assets",
            "localField": "asset",
            "foreignField": "_id",
            "as": "asset_doc"
        }},
        {"$unwind": "$asset_doc"},

        # 6 bis) récupérer l’ID du transmitter et le convertir si besoin
        {"$addFields": {
            "transmitterRaw": "$asset_doc.optionals.transmitter"
        }},
        {"$addFields": {
            "transmitterObj": {
                "$cond": [
                    { "$eq": [{ "$type": "$transmitterRaw" }, "objectId"] },
                    "$transmitterRaw",
                    { "$toObjectId": "$transmitterRaw" }
                ]
            }
        }},

        # 6 ter) lookup sur le transmitter pour obtenir son nom « humain »
        {
            "$lookup": {
                "from": "assets",
                "localField": "transmitterObj",
                "foreignField": "_id",
                "as": "tx_doc"
            }
        },
        {"$unwind": {"path": "$tx_doc", "preserveNullAndEmptyArrays": True}},

        # 6 quater) champs finaux utilisés partout
        {"$addFields": {
            "transmitter":     "$transmitterObj",   # id propre, tjs ObjectId
            "transmitterName": "$tx_doc.name"       # nom du transmitter
        }},

        {
        "$group": {              
            "_id": "$asset",
            "doc": { "$first": "$$ROOT" }
        }
        },
        { "$replaceRoot": { "newRoot": "$doc" } },



        # 7) FACET pour générer 4 sous-pipelines en une seule passe
        {"$facet": {
            # a) tous les MP mal configurés, dédupliqués et ordonnés
            "mis": [
                {"$match": {"misconfigured": True}},
                {"$addFields": {
                    "err_name": {
                        "$function": {
                            "lang": "js",
                            "args": ["$last_errcode", ERR_META_STR],
                            "body": "function(c,m){return m[String(c)]?m[String(c)].name:'ERR_'+c;}"
                        }
                    },
                    "severity": {
                        "$function": {
                            "lang": "js",
                            "args": ["$last_errcode", ERR_META_STR],
                            "body": "function(c,m){return m[String(c)]?m[String(c)].severity:'Unknown';}"
                        }
                    },
                    "cause": {
                        "$function": {
                            "lang": "js",
                            "args": ["$last_errcode", ERR_META_STR],
                            "body": "function(c,m){return m[String(c)]?m[String(c)].cause:'unknown';}"
                        }
                    }
                }},
                {"$project": {
                    "_id":      0,
                    "asset_id": "$asset",
                    "last_acq": {"$max": "$lastStats.acqend"},
                    "freq_err": 1,
                    "errcodes": 1,
                    "err_name": 1,
                    "severity": 1,
                    "cause":    1,
                    "transmitter":     1,
                    "transmitterName": 1
                }},
                {"$group": {
                    "_id":              "$asset_id",
                    "asset_id":         {"$first": "$asset_id"},
                    "last_acq":         {"$first": "$last_acq"},
                    "freq_err":         {"$first": "$freq_err"},
                    "errcodes":         {"$first": "$errcodes"},
                    "err_name":         {"$first": "$err_name"},
                    "severity":         {"$first": "$severity"},
                    "cause":            {"$first": "$cause"},
                    "transmitter":      {"$first": "$transmitter"},
                    "transmitterName":  {"$first": "$transmitterName"}
                }},
                {"$sort": {"transmitter": 1, "err_name": 1}}
            ],

            "bySeverity": [
                {"$match": {"misconfigured": True}},
                {"$addFields": {
                    "severity": {
                        "$function": {
                            "lang": "js",
                            "args": ["$last_errcode", ERR_META_STR],
                            "body": "function(c,m){return m[String(c)]?m[String(c)].severity:'Unknown';}"
                        }
                    }
                }
                },
                {"$group": {
                    "_id":   "$severity",
                    "count": {"$sum": 1}
                }},
                {"$sort": {"_id": -1}}
            ],

            # 1) Répartition par sévérité de **tous** les assets ayant au moins 1 stat
            "severityAll": [
                # on se base sur lastStats pour prendre la dernière sévérité
                { "$addFields": {
                    "last_severity": {
                    "$function": {
                        "lang": "js",
                        "args": ["$last_errcode", ERR_META_STR],
                        "body": "function(c,m){return m[String(c)]?m[String(c)].severity:'Unknown';}"
                    }
                    }
                }
                },
                { "$group": { "_id": "$last_severity", "count": { "$sum": 1 } } },
                { "$sort": { "_id": 1 } }
            ],

            

            # c) total de MP FAUTIFS PAR transmitter
            "byTransmitterFaulty": [
                {"$match": {"misconfigured": True}},
                {"$group": {
                    "_id":       "$transmitter",
                    "faultyMP":  {"$sum": 1}
                }}
            ],

            "dailyNew": [
                {"$match": {"misconfigured": True}},
                {"$group": {
                    "_id":   {"$dateToString": {"format": "%Y-%m-%d", "date": "$last_acq"}},
                    "count": {"$sum": 1}
                }},
                {"$sort": {"_id": 1}}
            ],


            # d) comptage global
            "total": [
                {"$count": "total_assets"}
            ]
        }}
    ]

    raw   = list(db["tasks"].aggregate(pipeline, allowDiskUse=True))[0]
    by_sev_mis   = raw.get("bySeverity", [])
    sev_all = raw.get("severityAll", [])
    daily_new = raw.get("dailyNew", [])

    # Liste des MP mal configurés
    items = [flatten_doc(d) for d in raw["mis"]]

    # Map des MP fautifs par transmitter
    fault_map = {f["_id"]: f["faultyMP"] for f in raw.get("byTransmitterFaulty", [])}

    # Tableau résumé par transmitter
    by_tx = [
        {
          "transmitter": tx,
          "totalMP":     total_map.get(tx, 0),
          "faultyMP":    fault_map.get(tx, 0)
        }
        for tx in set(total_map) | set(fault_map)
    ]

    # Annoter chaque MP fautif avec son totalMP (utile au front)
    for it in items:
        it["totalMP"] = total_map.get(it["transmitter"], 0)

    # Comptages
    tot     = raw["total"][0]["total_assets"] if raw["total"] else 0
    ko      = len(items)
    healthy = tot - ko

    return {
        "counts": {
            "total_assets":  tot,
            "misconfigured": ko,
            "healthy":       healthy
        },
        "items":         items,
        "byTransmitter": by_tx,
        "bySeverity":    by_sev_mis,
        "severityAll":   sev_all,
        "dailyNew":      daily_new
    }
