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
                "description": "Identifiant du client (ex. « Icare_Brussels »)"
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
                "description": "Projection MongoDB facultative : clés = champs à inclure/exclure, valeurs = 1 (inclure) ou 0 (exclure). Toujours inclure « address » pour identifier un document (ex. {\"address\":1,\"batt\":1,\"last_com\":1,\"_id\":0})."
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
    }

]

def _system_prompt(locale: str) -> str:
    """
    I-CARE Planner system-prompt generator.

    Responsibilities
    ----------------
    • Decide which FUNCTION to call, or reply directly.
    • Never return more than one function_call.
    • Distinguish clearly between:
        – query_db  → recherches **structurées** (find Mongo)   → pas de limite par défaut.
        – run_query → recherches **sémantiques / vectorielles** → `limit` OBLIGATOIRE ≤ 10 000.
    """

    # ------------------------------------------------------------------ #
    # 🇬🇧  English                                                         #
    # ------------------------------------------------------------------ #
    if locale.lower().startswith("en"):
        return (
            "You are I-CARE Planner. Decide which FUNCTION to call or reply directly.\n"
            "\n"
            "AVAILABLE FUNCTIONS\n"
            "1. describe_schema(client_id, collection)               → list fields in a collection.\n"
            "2. query_db(client_id, collection, filter, projection, limit)\n"
            "   • Plain Mongo find for **structured filters** (battery, RSSI, last_com…).\n"
            "   • No default limit: return **all** matching docs unless the user gives a number.\n"
            "3. connectivity_overview(client_id)                     → connected / disconnected counts.\n"
            "4. battery_overview(client_id)                          → battery status counters.\n"
            "5. rag_search(client_id, query)                         → unstructured / fallback search.\n"
            "6. run_query(db_name, coll, query, filter, limit, projection)\n"
            "   • Vector ($vectorSearch) when the user asks for semantic similarity or vague keywords.\n"
            "   • Must include a `limit` (k) 1-10 000. If omitted, set k = 100.\n"
            "\n"
            "RULES\n"
            "• Ask for fields           → describe_schema.\n"
            "• Pure structured filters  → query_db.\n"
            "  – If the user mentions specific fields, add `projection` with those fields + `address` (+ \"_id\":0).\n"
            "  – If the query contains “battery < N” or “batt < N”, build:\n"
            "        filter = {\"batt\": {\"$lt\": N}}\n"
            "        projection = {\"address\":1, \"batt\":1, \"last_com\":1, \"_id\":0}\n"
            "  – Do NOT add `limit` unless the user gives a number.\n"
            "• Keywords 'disconnected', 'offline' (no extra filters) → connectivity_overview.\n"
            "• Keywords 'battery status', 'critical', 'warning', 'ok' (no filters) → battery_overview.\n"
            "• Free-text, anomalies, unknown terms                   → run_query with `limit` (≤10 000).\n"
            "• If nothing applies                                    → rag_search.\n"
            "\n"
            "FEW-SHOT EXAMPLES\n"
            "User: \"What fields can I query on network_nodes?\"\n"
            "→ function_call: describe_schema(client_id, collection=\"network_nodes\")\n"
            "\n"
            "User: \"Give me all sensor IDs with batt < 3200\"\n"
            "→ function_call: query_db(\n"
            "      client_id,\n"
            "      collection=\"network_nodes\",\n"
            "      filter={\"batt\": {\"$lt\": 3200}},\n"
            "      projection={\"address\":1, \"_id\":0}\n"
            "  )\n"
            "\n"
            "User: \"Search for sensors similar to 'motor vibration anomaly'\"\n"
            "→ function_call: run_query(\n"
            "      db_name=\"Icare_Brussels\",\n"
            "      coll=\"network_nodes\",\n"
            "      query=\"motor vibration anomaly\",\n"
            "      limit=200,\n"
            "      projection={\"address\":1, \"score\":1, \"_id\":0}\n"
            "  )\n"
        )

    # ------------------------------------------------------------------ #
    # 🇫🇷  Français                                                       #
    # ------------------------------------------------------------------ #
    return (
        "Tu es I-CARE Planner. Décide quelle FONCTION appeler ou réponds directement.\n"
        "\n"
        "FONCTIONS DISPONIBLES\n"
        "1. describe_schema(client_id, collection)                    → liste les champs.\n"
        "2. query_db(client_id, collection, filter, projection, limit)\n"
        "   • Requête Mongo **structurée** (batt, RSSI, last_com…).\n"
        "   • Pas de limite par défaut : renvoie TOUS les documents si l'utilisateur ne donne pas de nombre.\n"
        "3. connectivity_overview(client_id)                          → capteurs connectés / déconnectés.\n"
        "4. battery_overview(client_id)                               → répartition états batterie.\n"
        "5. rag_search(client_id, query)                              → recherche texte libre.\n"
        "6. run_query(db_name, coll, query, filter, limit, projection)\n"
        "   • Recherche vectorielle ($vectorSearch) pour similarité sémantique / mots-clés vagues.\n"
        "   • `limit` OBLIGATOIRE (1-10 000). Si absent, mets 100.\n"
        "\n"
        "RÈGLES\n"
        "• Demande de champs                                         → describe_schema.\n"
        "• Filtres structurés (batt, rssi, last_com…)                 → query_db.\n"
        "  – Si l'utilisateur cite des champs précis, ajoute `projection` avec ces champs + `address` (+ \"_id\":0).\n"
        "  – Si la requête contient « batterie » ou « batt » suivi de « < N » :\n"
        "        filter = {\"batt\": {\"$lt\": N}}\n"
        "        projection = {\"address\":1, \"batt\":1, \"last_com\":1, \"_id\":0}\n"
        "  – N'ajoute pas `limit` sauf si l'utilisateur en parle.\n"
        "• Mots-clés « déconnectés », « hors-ligne » sans autres filtres → connectivity_overview.\n"
        "• Mots-clés « état batterie », « critique », « ok » sans filtres → battery_overview.\n"
        "• Requête libre / anomalie / floue                            → run_query avec `limit` ≤ 10 000.\n"
        "• Sinon                                                      → rag_search.\n"
        "\n"
        "EXEMPLES\n"
        "Utilisateur : « Quels champs puis-je interroger sur network_nodes ? »\n"
        "→ function_call: describe_schema(client_id, collection=\"network_nodes\")\n"
        "\n"
        "Utilisateur : « Donne-moi toutes les adresses avec batt < 3200 »\n"
        "→ function_call: query_db(\n"
        "      client_id,\n"
        "      collection=\"network_nodes\",\n"
        "      filter={\"batt\": {\"$lt\": 3200}},\n"
        "      projection={\"address\":1, \"_id\":0}\n"
        "  )\n"
        "\n"
        "Utilisateur : « Recherche les capteurs similaires à 'anomalie moteur' »\n"
        "→ function_call: run_query(\n"
        "      db_name=\"Icare_Brussels\",\n"
        "      coll=\"network_nodes\",\n"
        "      query=\"anomalie moteur\",\n"
        "      limit=200,\n"
        "      projection={\"address\":1, \"score\":1, \"_id\":0}\n"
        "  )\n"
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
