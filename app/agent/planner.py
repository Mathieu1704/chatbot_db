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
    },
    {
        "name": "query_multi_db",
        "description": "Interroge plusieurs bases Mongo pour récupérer des documents sur plusieurs clients à la volée.",
        "parameters": {
            "type": "object",
            "properties": {
                "client_ids": {
                    "type": "array",
                    "items": { "type": "string" },
                    "description": "Liste des identifiants de bases Mongo à interroger"
                },
                "collection": {
                    "type": "string",
                    "description": "Nom de la collection à interroger"
                },
                "filter": {
                    "type": "object",
                    "description": "Filtre MongoDB (dict) à appliquer"
                },
                "projection": {
                    "type": "object",
                    "description": "Champs à retourner, format {champ: 1}, inclure tous les champs mentionnés dans la question (ex. {\"address\": 1, \"batt\": 1, \"_id\": 0})"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum de documents à ramener par base ( à omettre si None)"
                }
            },
            "required": ["collection"]
        }
    },
    {
        "name": "get_asset_by_id",
        "description": "Récupère un document depuis la collection 'assets' d'une base MongoDB donnée (nom insensible à la casse) pour un ObjectId.",
        "parameters": {
            "type": "object",
            "properties": {
            "client_id": {
                "type": "string",
                "description": "Nom de la base (ex. “Cargill” ou “cargill”). Insensible à la casse."
            },
            "asset_id": {
                "type": "string",
                "description": "ObjectId (24 caractères hexadécimaux) de l’asset à récupérer."
            }
            },
            "required": ["client_id", "asset_id"]
        }
    },
    {
      "name": "misconfig_overview",
      "description": (
        "Retourne la liste des tasks/transmetteurs mal configurés "
        "pour une entreprise donnée."
      ),
      "parameters": {
        "type": "object",
        "properties": {
          "company": {
            "type": "string",
            "description": "Nom complet de l’entreprise (ex. ‘Icare Brussels’)"
          },
          "since_days": {
            "type": "integer",
            "description": "Période d’analyse en jours",
            "default": 30
          }
        },
        "required": ["company"]
      }
    },
    {
      "name": "misconfig_multi_overview",
      "description": (
        "Retourne la liste des tasks/transmetteurs mal configurés "
        "sur plusieurs entreprises à la fois."
      ),
      "parameters": {
        "type": "object",
        "properties": {
          "client_ids": {
            "type": "array",
            "items": { "type": "string" },
            "description": (
              "Liste des noms de bases Mongo (ex. ['Icare_Brussels','Cabot']); "
              "omis ⇒ toutes"
            )
          },
          "since_days": {
            "type": "integer",
            "description": "Période d’analyse en jours",
            "default": 30
          }
        }
      }
    }

]

def _system_prompt(locale: str) -> str:
    """
    I-CARE Planner – system prompt (FR / EN).

    📌 PRINCIPES GÉNÉRAUX
    • À chaque tour, choisis **UNE SEULE** fonction ou réponds directement.
    • Ne génère jamais plus d’un `function_call`.
    • Bien distinguer :
        – `query_db`      : requêtes Mongo « structurées » (find + filtres précis).
        – `query_multi_db`: même chose mais sur plusieurs bases.
        – `run_query`     : recherche vectorielle / sémantique (`$vectorSearch`).
    • Si aucune de ces fonctions ne convient → `rag_search`.

    ──────────────────────────────────────────────────────────────────────
    RÈGLES DE DÉCISION
    ──────────────────────────────────────────────────────────────────────
    1. **Clarification de schéma**  
       « Quels sont/what are the fields ? »      → `describe_schema`.

    2. **Topologie réseau** (gateways, capteurs, range-extenders…)  
       Mots-clés réseau → `network_topology`.

    3. **Statut de connexion hors-ligne**  
       « offline / hors-ligne » sans autre filtre → `connectivity_overview`.

    4. **Batteries**  
       « état batterie / critical / warning / ok » → `battery_overview`.  
       Détail d’une catégorie → `battery_list`.

    5. **Filtres explicites** (`batt`, `rssi`, `last_com`, `node_type`, etc.)  
       → `query_db` **ou** `query_multi_db` selon qu’il y a un ou plusieurs
         clients dans la question.

    6. **Recherche floue / anomalie / similarité / texte libre**  
       → `run_query` (toujours avec un `limit` ≤ 10 000, `k` = 100 par défaut).

    7. **Tasks mal configurées / misconfigured / bad task” → misconfig_overview ou misconfig_multi_overview si plusieurs bases citées.

    8. **Sinon** → `rag_search`.

    ──────────────────────────────────────────────────────────────────────
    GESTION DES COLLECTIONS
    ──────────────────────────────────────────────────────────────────────
    • Si la question contient le nom exact (ou approchant) d’une collection
      Mongo **connue**  
      (`network_nodes`, `analyses`, `assets`, `alarms`, `faults`, `contacts`,
       `kpis`, `media.files`, `media.chunks`, `groups`, `gateways_status`,
       `preselections`, `processing`, `profiles`, etc.)  
      alors place ce nom dans la clé `collection` de `query_db` /
      `query_multi_db`.

    • **Cas particulier : `network_nodes`**
        - Si la question mentionne gateway / sensor / extender …  
          ajoute automatiquement le filtre `{"node_type": 1|2|3}`.
        - Si des champs spécifiques sont demandés → construis `projection`
          avec ces champs **+ `address`** et masque `_id` si non nécessaire.
        - Si aucun champ n’est cité (ex : donne moi tous les capteurs/gateways/extenders de Eurial) → **AJOUTE OBLIGATOIREMENT ** la projection : `{"address":1,"batt":1,"last_com":1,"_id":0}`.

    • **Toutes les autres collections**  
        - Si la question **nomme** un ou plusieurs champs → mets-les dans
          `projection` (ex. `{"status":1,"planned_date":1,"_id":0}`).
        - Si aucun champ n’est mentionné → laisse `projection` vide (= tous
          les champs) afin de renvoyer le document complet.
        - Ne jamais injecter d’`address` ni de `node_type` si ces champs
          n’existent pas.

    ──────────────────────────────────────────────────────────────────────
    CHOIX ENTRE `query_db` ET `query_multi_db`
    ──────────────────────────────────────────────────────────────────────
    • La question cite **un seul** client explicite  
      → `query_db(client_id=<unique>, collection=…, …)`.

    • La question cite **plusieurs** clients (« chez Eurial **et** Cabot »…)  
      → `query_multi_db(client_ids=[…], collection=…, …)`.

    • AUCUN client explicite (« sur toutes les bases »…)  
      → `query_multi_db` **sans** propriété `client_ids`
        (le backend interrogera toutes les bases).

    ──────────────────────────────────────────────────────────────────────
    STRUCTURE DES ARGUMENTS
    ──────────────────────────────────────────────────────────────────────
    • Chaque clé de `filter` est indépendante :

      ✔️ correct
      ```json
      "filter": {
        "batt":      { "$lte": 3800 },
        "node_type": 2
      }
      ```

      ❌ incorrect
      ```json
      "filter": {
        "batt": { "$lte": 3800, "node_type": 2 }
      }
      ```


    ──────────────────────────────────────────────────────────────────────
    EXEMPLES
    ──────────────────────────────────────────────────────────────────────
    • « Montre tous les capteurs avec batt < 3 200 »  
      → `query_db(client_id, "network_nodes",
                  filter={"batt":{"$lt":3200},"node_type":2},
                  projection={"address":1,"batt":1,"_id":0})`

    • « List gateways that haven’t communicated for 48 h »  
      → `query_db(client_id, "network_nodes",
                  filter={"node_type":1,
                          "last_com":{"$lt":"<ISO-date-48h-ago>"}} ,
                  projection={"address":1,"last_com":1,"_id":0})`

    • « Donne-moi toutes les analyses de Cabot »  
      → `query_db("Cabot", "analyses",
                  filter={},              # aucun filtre
                  projection={},          # renvoie tout le document
                  limit=100000)`

    • « Status et planned_date des analyses chez Eurial et Cabot »  
      → `query_multi_db(client_ids=["Eurial","Cabot"], "analyses",
                        filter={},  # pas de condition
                        projection={"status":1,"planned_date":1,"_id":0})`

    • « Trouve les capteurs similaires à “motor vibration anomaly” »  
      → `run_query(db_name, "network_nodes",
                   query="motor vibration anomaly",
                   limit=200,
                   projection={"address":1,"score":1,"_id":0})`
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
