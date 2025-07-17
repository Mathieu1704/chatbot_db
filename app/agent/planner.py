import os
import json
from openai import AsyncOpenAI

_openai_key = os.getenv("OPENAI_API_KEY")
client = AsyncOpenAI(api_key=_openai_key)

# Schemas des fonctions que l’IA peut appeler
FUNC_SCHEMAS = [
    {
        "name": "connectivity_overview",
        "description": (
            "Retourne l'état global des capteurs pour une entreprise donnée : "
            "- nombre de capteurs connectés, "
            "- nombre de capteurs déconnectés, "
            "- nombre total de capteurs, "
            "- aperçu des 10 premiers capteurs hors-ligne."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "company": {
                    "type": "string",
                    "description": "Nom complet de l'entreprise (ex. 'Icare Brussels', 'Icare Mons', etc.)"
                }
            },
            "required": ["company"]
        }
    },
    {
        "name": "battery_overview",
        "description": "Retourne l'état des batteries : critique (<critical), attention (>=critical et <warning), ok (>=warning).",
        "parameters": {
            "type": "object",
            "properties": {
            "company": {
                "type": "string",
                "description": "Nom complet de l'entreprise"
            },
            "critical_threshold": {
                "type": "integer",
                "description": "Seuil critique en mV",
                "default": 3200
            },
            "warning_threshold": {
                "type": "integer",
                "description": "Seuil d'alerte en mV",
                "default": 3500
            }
            },
            "required": ["company"]
        }
    },
    {
        "name": "battery_list",
        "description": "Récupère la liste des adresses pour une catégorie de batterie.",
        "parameters": {
            "type": "object",
            "properties": {
            "company": {
                "type": "string",
                "description": "Nom complet de l'entreprise"
            },
            "category": {
                "type": "string",
                "enum": ["critical", "warning", "ok"],
                "description": "Catégorie souhaitée"
            },
            "critical_threshold": {
                "type": "integer",
                "description": "Seuil critique en mV",
                "default": 3200
            },
            "warning_threshold": {
                "type": "integer",
                "description": "Seuil d'alerte en mV",
                "default": 3500
            }
            },
            "required": ["company", "category"]
        }
    },
    {
      "name": "run_query",
      "description": "Recherche vectorielle + filtres dans network_nodes.",
      "parameters": {
        "type": "object",
        "properties": {
          "db_name": {"type": "string", "description": "Nom de la base"},
          "coll":    {"type": "string", "description": "Nom de la collection"},
          "query":   {"type": "string", "description": "Phrase en langage naturel"},
          "filter":  {"type": "object", "description": "Filtres Mongo optionnels"},
          "limit":   {"type": "integer"}
        },
        "required": ["db_name", "coll", "query"]
      }
    },
    {
      "name": "describe_schema",
      "description": "Retourne la liste des champs d'une collection MongoDB pour un client donné",
      "parameters": {
        "type": "object",
        "properties": {
          "client_id": {"type": "string", "description": "Identifiant du client"},
          "collection": {"type": "string", "description": "Nom de la collection"}
        },
        "required": ["client_id","collection"]
      }
    },
    {
        "name": "query_db",
        "description": "Exécute une requête Mongo générique pour récupérer des documents",
        "parameters": {
            "type": "object",
            "properties": {
            "client_id": {
                "type": "string",
                "description": "Identifiant du client (ex. « Icare_Brussels », \"Cabot\", etc.)"
            },
            "collection": {
                "type": "string",
                "description": "Nom de la collection (ex. « network_nodes »)"
            },
            "filter": {
                "type": "object",
                "description": "Critères de filtrage MongoDB (opérateurs autorisés : $eq, $lt, $gt, etc.)"
            },
            "limit": {
                "type": "integer",
                "description": "Nombre maximum de documents à retourner",
                "default": 100000
            },
            "projection": {
                "type": "object",
                "description": "Projection MongoDB facultative : clés = champs à inclure/exclure, valeurs = 1 (inclure) ou 0 (exclure). Toujours inclure « address » pour identifier un document (ex. {\"address\":1,\"batt\":1,\"last_com\":1,\"_id\":0}). Toujours faire une projection pour masquer tous les éléments non nécessaire."
            }
            },
            "required": ["client_id", "collection"]
        }
    },
    {
        "name": "rag_search",
        "description": "Recherche sémantique dans la base si la question dépasse les simples stats.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Question ou critères libres"
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "network_topology",
        "description": (
            "Reconstruit la topologie réseau (gateways, range-extenders, sensors) "
            "pour une entreprise donnée."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "company": {
                    "type": "string",
                    "description": "Nom complet de l’entreprise (ex. 'Icare Brussels')"
                }
            },
            "required": ["company"]
        }
    }
]

def _system_prompt(locale: str) -> str:
    """
    I-CARE Planner – system prompt.

    Objectifs ―
      • Choisir UNE fonction à appeler, ou répondre directement.
      • Ne jamais produire plus d’un `function_call`.
      • Distinguer clairement :
          – query_db  : requêtes Mongo “structurées” (find + filtres précis)
          – run_query : recherche vectorielle / sémantique ($vectorSearch)

    Règles communes ―
      • Si l’utilisateur demande « quels champs » → describe_schema.
      • Si la question contient des noms type capteurs, gateway, etc, ou uniquement des filtres explicites
        (batt, rssi, last_com, node_type…)        → query_db.
      • Si la question contient des mots-clés flous
        (anomalie, tendance, similarité, texte libre…) → run_query
        (toujours avec un `limit` ≤ 10 000, k = 100 par défaut).
      • « offline / hors-ligne » sans autres filtres → connectivity_overview.
      • « état batterie » / critical / warning / ok  → battery_overview.
      • Sinon                                      → rag_search.

    Conseils projection ―
      • Lorsque query_db inclut des champs spécifiques,
        ajouter `projection` avec ces champs + `address`
        et masquer « _id » si non nécessaire.

    Conseils node_type ―
      • Si la question parle de *gateway / passerelle* → ajouter filter {"node_type": 1}.
      • Si elle parle de *capteurs / sensors / transmitters* → filter {"node_type": 2}.
      • Si elle parle de *range extender*                → filter {"node_type": 3}.
      • Ne mélange pas plusieurs `node_type` dans la même requête.

    Exemples ―
      • “Show all sensor IDs with batt < 3 200”  
        → query_db(client_id, "network_nodes",
                   filter={"batt":{"$lt":3200}, "node_type":2},
                   projection={"address":1,"batt":1,"_id":0})

      • “List gateways that haven’t communicated for 48 h”  
        → query_db(client_id, "network_nodes",
                   filter={"node_type":1,
                           "last_com":{"$lt":"<ISO-date-48h-ago>"}},
                   projection={"address":1,"last_com":1,"_id":0})

      • “Find sensors similar to ‘motor vibration anomaly’ ”  
        → run_query(db_name, "network_nodes",
                     query="motor vibration anomaly",
                     limit=200,
                     projection={"address":1,"score":1,"_id":0})
    """

    # English variant ---------------------------------------------------
    if locale.lower().startswith("en"):
        return (
            "You are I-CARE Planner. Decide which FUNCTION to call or reply directly.\n"
            + _system_prompt.__doc__
        )

    # French variant ----------------------------------------------------
    return (
        "Tu es I-CARE Planner. Décide quelle FONCTION appeler ou réponds directement.\n"
        + _system_prompt.__doc__
    )




async def plan(messages: list[dict], locale: str = "fr") -> dict:
    """
    Demande à GPT quel outil appeler en fonction de l'historique `messages`.
    Retourne soit :
      • {"name": <fonction>, "arguments": <dict>} pour un appel de fonction,
      • {"name": "answer", "content": <str>} si aucune fonction à appeler,
      • {"name": "unknown"} si la requête ne correspond à aucun cas.
    """
    payload = [
        {"role": "system", "content": _system_prompt(locale)},
        *messages
    ]
    resp = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=payload,
        functions=FUNC_SCHEMAS,
        function_call="auto",
        temperature=0
    )
    msg = resp.choices[0].message

    if msg.function_call:
        return {
            "name": msg.function_call.name,
            "arguments": json.loads(msg.function_call.arguments or "{}")
        }

    # Aucun appel de fonction → réponse directe ou unknown
    text = msg.content.strip()
    if text.lower() in ("unknown", "je ne sais pas", "désolé"):
        return {"name": "unknown"}
    return {"name": "answer", "content": text}
