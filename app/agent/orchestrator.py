import time
import traceback
import uuid
import os
import json
from dotenv import load_dotenv
from typing import Any, Dict, Optional

from cachetools import TTLCache, cached

from app.tools import sensor_tools as st
from app.tools.sensor_tools import battery_overview, battery_list
from app.tools.topology import get_network_topology, topology_to_d3
from app.rag.vector_store import query_sensors
from app.agent import planner, answerer
from app.db import list_companies, find_company_candidates, execute_db_query, describe_schema
from app.utils.slugify_company import slugify_company
from app.utils.serialize import serialize_docs
from app.search.run_query import run_query
from app.agent.state import PENDING, CONVERSATIONS

# ---------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------
load_dotenv()
BATTERY_CRITICAL_DEFAULT = int(os.getenv("BATTERY_CRITICAL", "3200"))
BATTERY_WARNING_DEFAULT  = int(os.getenv("BATTERY_WARNING", "3500"))

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def resolve_company(raw: str) -> Optional[str]:
    """Essaie de faire correspondre le texte libre à un nom complet d’entreprise."""
    cands = find_company_candidates(raw)
    if not cands:
        for comp in list_companies():
            if slugify_company(comp).endswith(raw.lower()):
                return comp
        return None
    return cands[0]

# ---------------------------------------------------------------------
# Cache 1 minute pour l’overview
# ---------------------------------------------------------------------
_overview_cache = TTLCache(maxsize=100, ttl=60)

@cached(_overview_cache)
def cached_overview(company: str) -> Dict[str, Any]:
    return st.connectivity_overview(company)

# ---------------------------------------------------------------------
# Orchestrateur principal
# ---------------------------------------------------------------------
async def handle_query(
    text: str,
    locale: str = "fr",
    session_id: str | None = None
) -> Dict[str, Any]:
    # 0) Session
    if not session_id:
        session_id = str(uuid.uuid4())
    print(f"[DEBUG] ← SESSION {session_id} – Received text: \"{text}\"", flush=True)
    print(f"[STATE] pending keys before handling: {list(PENDING.keys())}", flush=True)

    start = time.time()

    # 1) Si la session est en attente d’une précision utilisateur
    pending = PENDING.get(session_id)
    if pending and pending["func_name"] == "connectivity_overview":
        raw = text.strip()
        cands = find_company_candidates(raw)
        print(f"[DEBUG] pending branch – find_company_candidates('{raw}') → {cands}", flush=True)

        # 1a) Un seul candidat → on exécute
        if len(cands) == 1:
            matched = cands[0]
            data = cached_overview(company=matched)
            del PENDING[session_id]
            return {
                "session_id": session_id,
                "answer": await answerer.answer(locale, data, pending["original_text"]),
                "duration_ms": int((time.time() - start) * 1000)
            }

        # 1b) Plusieurs ou aucun → nouvelle clarification
        clarify_payload = {
            "clarify": {
                "field": "company",
                "raw": raw,
                "candidates": cands
            }
        }
        return {
            "session_id": session_id,
            "answer": await answerer.answer(locale, clarify_payload, pending["original_text"])
        }

    # 2) Pas de pending → on prépare le contexte pour le planner
    convo = CONVERSATIONS.setdefault(
        session_id,
        [{"role": "system", "content": "Tu es I-CARE Planner. Décide quelle FONCTION appeler en fonction de la requête."}]
    )
    convo.append({"role": "user", "content": text})
    print(f"[STATE] CONVERSATIONS length: {len(convo)}", flush=True)

    # 3) Planification
    step1 = await planner.plan(convo, locale)
    func_name = step1.get("name")
    func_args = step1.get("arguments", {})
    
    pretty_args = json.dumps(func_args, indent=2, ensure_ascii=False)
    print(f"[PLANNER] → fonction: {func_name} | args: {pretty_args}", flush=True)

    # A) Le LLM répond directement
    if func_name in {"answer", "unknown"}:
        answer_txt = step1.get("content", "Désolé, je ne peux pas répondre à cette question.")
        return {"session_id": session_id, "answer": answer_txt}

    # B) Exécution de la fonction demandée
    try:
        # -----------------------------------------------------------------
        # Connectivity Overview
        # -----------------------------------------------------------------
        if func_name == "connectivity_overview":
            raw     = func_args.get("company", "").strip()
            matched = resolve_company(raw)
            if not matched:
                PENDING[session_id] = {
                    "func_name": func_name,
                    "func_args": func_args,
                    "original_text": text
                }
                clarify_payload = {
                    "clarify": {
                        "field": "company",
                        "raw": raw,
                        "candidates": find_company_candidates(raw)
                    }
                }
                return {
                    "session_id": session_id,
                    "answer": await answerer.answer(locale, clarify_payload, text)
                }

            # ── appel du helper corrigé ───────────────────────────────────────
            data = cached_overview(company=matched)          # contient items + *_count

            # ── normalisation des items ───────────────────────────────────────
            items = []
            for d in data["items"]:
                d = {**d}                     # copie
                d["battery"] = d.pop("batt", None)  # rename batt -> battery
                items.append(d)
            docs = serialize_docs(items)

            columns = ["address", "battery", "parent", "rssi", "last_com"]

            answer_txt = await answerer.answer(
                locale,
                {
                    "items": docs,
                    "connected_count":    data["connected_count"],
                    "disconnected_count": data["disconnected_count"]
                },
                text
            )

            return {
                "session_id": session_id,
                "answer": answer_txt,
                "documents": docs,
                "columns": columns,
                "duration_ms": int((time.time() - start) * 1000)
            }



        # -----------------------------------------------------------------
        # run_query (vector search + filtres)
        # -----------------------------------------------------------------
        elif func_name == "run_query":
            docs = run_query(
                db_name=func_args["db_name"],
                coll=func_args.get("coll", "network_nodes"),
                query=func_args["query"],
                filter_json=func_args.get("filter", {}),
                k=func_args.get("limit"),
                num_candidates=func_args.get("num_candidates"),
                projection=func_args.get("projection"),
                index_name=func_args.get("index_name")
            )
            return {
                "session_id": session_id,
                "answer": f"{len(docs)} capteurs trouvés (batt < 3500 mV, hors ligne ≥ 4 j)",
                "documents": docs,                  # ← brut JSON, prêt pour TanStack
                "columns": list(docs[0].keys()) if docs else [],
                "duration_ms": int((time.time() - start) * 1000)
            }


        # -----------------------------------------------------------------
        # rag_search (full-text fallback)
        # -----------------------------------------------------------------
        elif func_name == "rag_search":
            qry = func_args.get("query", "")
            snippets = query_sensors(qry, k=3)
            return {
                "session_id": session_id,
                "answer": await answerer.answer(locale, {"snippets": snippets}, text),
                "duration_ms": int((time.time() - start) * 1000)
            }

        # -----------------------------------------------------------------
        # battery_overview
        # -----------------------------------------------------------------
        elif func_name == "battery_overview":
            comp_raw = func_args.get("company", "").strip()
            comp = resolve_company(comp_raw)
            if not comp:
                return {"session_id": session_id,
                        "answer": f"Je ne reconnais pas l’entreprise « {comp_raw} »."}

            crit = int(func_args.get("critical_threshold", BATTERY_CRITICAL_DEFAULT))
            warn = int(func_args.get("warning_threshold", BATTERY_WARNING_DEFAULT))
            data = battery_overview(comp, crit, warn)
            return {
                "session_id": session_id,
                "answer": await answerer.answer(locale, data, text),
                "duration_ms": int((time.time() - start) * 1000)
            }

        # -----------------------------------------------------------------
        # battery_list (détails par catégorie)
        # -----------------------------------------------------------------
        elif func_name == "battery_list":
            comp_raw = func_args.get("company", "").strip()
            comp = resolve_company(comp_raw)
            if not comp:
                return {"session_id": session_id,
                        "answer": f"Je ne reconnais pas l’entreprise « {comp_raw} »."}

            crit = int(func_args.get("critical_threshold", BATTERY_CRITICAL_DEFAULT))
            warn = int(func_args.get("warning_threshold", BATTERY_WARNING_DEFAULT))
            tool_result = battery_list(comp, func_args.get("category"), crit, warn)
            cat  = tool_result.get("category")
            addrs = tool_result.get("addresses", [])
            header = (
                f"**Battery {cat.title()}** – {len(addrs)} nodes"
                if locale.lower().startswith("en")
                else f"**Liste des batteries « {cat} »** – {len(addrs)} capteurs"
            )
            lines = [f"- {addr}" for addr in addrs]
            return {
                "session_id": session_id,
                "answer": "\n".join([header] + lines),
                "duration_ms": int((time.time() - start) * 1000)
            }

        # -----------------------------------------------------------------
        # describe_schema
        # -----------------------------------------------------------------
        elif func_name == "describe_schema":
            args = func_args
            fields = describe_schema(
                client_id=args["client_id"],
                collection=args["collection"]
            )
            return {"session_id": session_id, "fields": fields}

        # -----------------------------------------------------------------
        # query_db (find classique)
        # -----------------------------------------------------------------
        elif func_name == "query_db":
            args      = func_args
            raw_text  = text                              # requête utilisateur brute

            # ───────────────────────────────────────────────────────────────
            # 1) Résolution du client
            # ───────────────────────────────────────────────────────────────
            probe = find_company_candidates(raw_text)     # cherche un nom dans la question
            if probe:                                     # ≥ 1 candidat trouvé
                client_id = probe[0]
                if client_id != args["client_id"]:
                    print(f"[ORCH] override client_id '{args['client_id']}' -> '{client_id}'",
                          flush=True)
            else:                                         # fallback : tentative de correction
                client_id = resolve_company(args["client_id"]) or args["client_id"]

            # ───────────────────────────────────────────────────────────────
            # 2) Correction automatique du node_type selon le wording
            # ───────────────────────────────────────────────────────────────
            txt = raw_text.lower()
            if any(w in txt for w in
                   ["capteur", "capteurs", "sensor", "sensors",
                    "transmitter", "transmitters"]):
                args.setdefault("filter", {})["node_type"] = 2
            elif any(w in txt for w in
                     ["gateway", "gateways", "passerelle", "passerelles"]):
                args.setdefault("filter", {})["node_type"] = 1
            elif any(w in txt for w in
                     ["range extender", "extender"]):
                args.setdefault("filter", {})["node_type"] = 3

            # 2bis) projection par défaut si GPT n'en a pas fourni
            if not args.get("projection"):
                args["projection"] = {
                    "address":   1,
                    "batt":      1,
                    "last_com":  1,
                    "_id":       0
                }

            # ───────────────────────────────────────────────────────────────
            # 3) Exécution de la requête Mongo
            # ───────────────────────────────────────────────────────────────
            raw_docs = execute_db_query(
                client_id  = client_id,                   # nom de base validé
                collection = args["collection"],
                filter     = args.get("filter"),
                projection = args.get("projection"),
                limit      = args.get("limit")
            )

            docs = serialize_docs(raw_docs)
            cols = list(docs[0].keys()) if docs else []

            answer_txt = await answerer.answer(locale, {"documents": docs}, text)

            return {
                "session_id": session_id,
                "answer":      answer_txt,
                "documents":   docs,
                "columns":     cols,
                "duration_ms": int((time.time() - start) * 1000)
            }
        # -----------------------------------------------------------------
        # get_network_topology
        # -----------------------------------------------------------------
        elif func_name == "network_topology":
            raw = func_args.get("company", "").strip()
            comp = resolve_company(raw)
            if not comp:
                return {
                    "session_id": session_id,
                    "answer": f"Je ne reconnais pas l’entreprise « {raw} »."
                }

            topo_json = get_network_topology(comp)
            d3_data   = topology_to_d3(topo_json)   # format {nodes, links}

            return {
                "session_id": session_id,
                # ↙︎ résumé pour l’utilisateur
                "answer": await answerer.answer(
                    locale,
                    {"topology": topo_json},  # passe un dict, pas une liste
                    text
                ),
                "company": comp,          
                "topology": topo_json,
                "graph": d3_data,
                "duration_ms": int((time.time() - start) * 1000)
            }



        # -----------------------------------------------------------------
        # Fonction non implémentée
        # -----------------------------------------------------------------
        else:
            return {"session_id": session_id,
                    "answer": f"⚠️ Fonction non implémentée : {func_name}"}

    except Exception as exc:
        traceback.print_exc()
        return {"session_id": session_id,
                "answer": f"⚠️ Erreur côté serveur : {exc}"}
