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
from app.tools.dynamic_projection import build_dynamic_projection, build_dynamic_projection_multi
from app.tools.misconfiguration import detect_misconfig
from app.rag.vector_store import query_sensors
from app.agent import planner, answerer
from app.db import list_companies, find_company_candidates, execute_db_query, describe_schema, execute_cross_db_query, sample_fields, get_asset_by_id
from app.utils.slugify_company import slugify_company
from app.utils.serialize import serialize_docs, extract_columns, clean_jsonable
#from app.search.run_query import run_query
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


        
        # # -----------------------------------------------------------------
        # # run_query (vector search + filtres)
        # # -----------------------------------------------------------------
        # elif func_name == "run_query":
        #     docs = run_query(
        #         db_name=func_args["db_name"],
        #         coll=func_args.get("coll", "network_nodes"),
        #         query=func_args["query"],
        #         filter_json=func_args.get("filter", {}),
        #         k=func_args.get("limit"),
        #         num_candidates=func_args.get("num_candidates"),
        #         projection=func_args.get("projection"),
        #         index_name=func_args.get("index_name")
        #     )
        #     return {
        #         "session_id": session_id,
        #         "answer": f"{len(docs)} capteurs trouvés (batt < 3500 mV, hors ligne ≥ 4 j)",
        #         "documents": docs,                  # ← brut JSON, prêt pour TanStack
        #         "columns": list(docs[0].keys()) if docs else [],
        #         "duration_ms": int((time.time() - start) * 1000)
        #     }
        
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
            if args["collection"] == "network_nodes": 
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

            # ───────────────────────────────────────────────────────────────
            # 2bis) Si on fait de la projection dynamique, on récupère directement
            #     les documents via build_dynamic_projection (aggregate pipeline).
            # ───────────────────────────────────────────────────────────────
            if args["collection"] != "network_nodes" and not args.get("projection"):
                print(f"[ORCH] → dynamic aggregation pour {client_id}.{args['collection']}")
                # build_dynamic_projection renvoie directement la liste de docs
                raw_docs = await build_dynamic_projection(
                    client_id=client_id,
                    collection=args["collection"],
                    user_query=raw_text,
                    match_filter=args.get("filter") or {}
                )
            else:
                # fallback sur un find classique si pas de dynamic
                # assure la projection / filter existants
                proj = args.get("projection") or {}
                for k in (args.get("filter") or {}):
                    if not k.startswith("$") and k not in proj:
                        proj[k] = 1
                raw_docs = execute_db_query(
                    client_id  = client_id,
                    collection = args["collection"],
                    filter     = args.get("filter"),
                    projection = proj,
                    limit      = args.get("limit")
                )

            for d in raw_docs:
                d["_company"] = client_id

            docs = serialize_docs(raw_docs)
            cols = extract_columns(docs)
            if "_company" not in cols:
                cols.insert(0, "_company")  # assure que _company est en 1ère position

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
        # execute_cross_db_query
        # -----------------------------------------------------------------
        elif func_name == "query_multi_db":
            args     = func_args
            raw_text = text.lower()

            # ── Injection automatique de node_type selon le wording comme dans query_db
            if args["collection"] == "network_nodes":
                if any(w in raw_text for w in ["capteur", "capteurs", "sensor", "sensors"]):
                    args.setdefault("filter", {})["node_type"] = 2
                elif any(w in raw_text for w in ["gateway", "gateways", "passerelle", "passerelles"]):
                    args.setdefault("filter", {})["node_type"] = 1
                elif any(w in raw_text for w in ["range extender", "extender"]):
                    args.setdefault("filter", {})["node_type"] = 3

            raw_ids = args.get("client_ids")
            print(f"[DEBUG][orchestrator] Raw client_ids from LLM: {raw_ids}", flush=True)

            # 1) Déterminer la liste des clients à interroger
            if not raw_ids:
                clients = list_companies()
                print(f"[DEBUG][orchestrator] No client_ids provided, defaulting to all companies: {clients}", flush=True)
            else:
                clients = [resolve_company(raw) or raw for raw in raw_ids]
                print(f"[DEBUG][orchestrator] Resolved client_ids to actual DB names: {clients}", flush=True)

            # Trier alphabétiquement
            clients = sorted(clients, key=str.lower)
            print(f"[DEBUG][orchestrator] Sorted client list: {clients}", flush=True)

            # 2) Si pas de projection (hors network_nodes), faire dynamic aggregation multi-DB
            if args["collection"] != "network_nodes" and not args.get("projection"):
                print(f"[ORCH-MULTI] → dynamic aggregation multi-DB pour "
                      f"{args['collection']} sur {len(clients)} bases")
                raw_docs = await build_dynamic_projection_multi(
                    client_ids=clients,
                    collection=args["collection"],
                    user_query=raw_text,
                    match_filter=args.get("filter") or {}
                )

            else:
                # fallback : ensure projection includes filter keys
                proj = args.get("projection") or {}
                for k in (args.get("filter") or {}):
                    if not k.startswith("$") and k not in proj:
                        proj[k] = 1
                print(f"[DEBUG][orchestrator] Final projection used: {proj}", flush=True)
                raw_docs = execute_cross_db_query(
                    client_ids = clients,
                    collection = args["collection"],
                    filter     = args.get("filter"),
                    projection = proj,
                    limit      = args.get("limit")
                )

            # 3) Réordonner les résultats par client
            raw_docs.sort(key=lambda d: d["_company"].lower())
            print(f"[DEBUG][orchestrator] Retrieved {len(raw_docs)} documents in total", flush=True)

            # 4) Sérialisation et formatage de la réponse
            docs    = serialize_docs(raw_docs)
            columns = extract_columns(docs)
            print(f"[DEBUG][orchestrator] Columns to display: {columns}", flush=True)

            answer_txt = await answerer.answer(
                locale,
                {"documents": docs},
                text
            )
            print(f"[DEBUG][orchestrator] Generated answer text", flush=True)

            return {
                "session_id": session_id,
                "answer":      answer_txt,
                "documents":   docs,
                "columns":     columns,
                "duration_ms": int((time.time() - start) * 1000)
            }

        # -----------------------------------------------------------------
        # get_asset_by_id
        # -----------------------------------------------------------------
        elif func_name == "get_asset_by_id":
            client_id = func_args["client_id"]
            asset_id  = func_args["asset_id"]

            asset_doc = get_asset_by_id(client_id, asset_id)
            if not asset_doc:
                return {
                    "session_id": session_id,
                    "answer": f"❌ Asset {asset_id} introuvable dans la base {client_id}."
                }

            # Sérialisation plate + colonnes
            flat = serialize_docs([asset_doc])[0]
            cols = extract_columns([flat])

            # Génération de la réponse utilisateur
            answer_txt = await answerer.answer(
                locale,
                {"documents": [flat]},
                f"Détail de l’asset {asset_id}"
            )
            return {
                "session_id": session_id,
                "answer":    answer_txt,
                "documents": [flat],
                "columns":   cols
            }

        # -----------------------------------------------------------------
        # misconfig_overview
        # -----------------------------------------------------------------
        elif func_name == "misconfig_overview":
            # 1) Résolution du nom de la base
            comp_raw = func_args.get("company", "").strip()
            comp = resolve_company(comp_raw)
            if not comp:
                return {
                    "session_id": session_id,
                    "answer": f"Je ne reconnais pas l’entreprise « {comp_raw} »."
                }

            # 2) Appel du helper
            since = int(func_args.get("since_days", 30))
            res = detect_misconfig(comp, since)

            # 3) Ajout de _company aux items
            for item in res["items"]:
                item["_company"] = comp

            # 4) Sérialisation des items
            docs = serialize_docs(res["items"])
            cols = extract_columns(docs)

            # 5) Formatage de la réponse via answerer
            answer_txt = await answerer.answer(
                locale,
                {"counts": res["counts"], "documents": docs},
                text
            )

            payload = {
                "session_id":  session_id,
                "answer":      answer_txt,
                # tableau
                "documents":   docs,
                "columns":     cols,
                # graphes
                "counts":         res["counts"],
                "byTransmitter":  res["byTransmitter"],
                "bySeverity":     res["bySeverity"],
                "dailyNew":       res["dailyNew"],
                "duration_ms": int((time.time() - start) * 1000)
            }

            # ── NOUVEAU : nettoyage JSON-safe ─────────────────────────────
            return clean_jsonable(payload)



        # -----------------------------------------------------------------
        # misconfig_multi_overview
        # -----------------------------------------------------------------
        elif func_name == "misconfig_multi_overview":
            # 1) Liste des bases à interroger
            raw_ids = func_args.get("client_ids") or list_companies()
            since   = int(func_args.get("since_days", 30))

            # 2) Agréger tous les items avec _company
            all_items = []
            for raw in sorted(raw_ids, key=str.lower):
                comp = resolve_company(raw) or raw
                res  = detect_misconfig(comp, since)

                for item in res["items"]:
                    item["_company"] = comp
                all_items.extend(res["items"])

            # 3) Sérialisation
            docs = serialize_docs(all_items)
            cols = extract_columns(docs)

            # 4) Retour JSON (comme execute_cross_db_query)
            answer_txt = await answerer.answer(
                locale,
                {"documents": docs},
                text
            )
            payload = {
                "session_id":  session_id,
                "answer":      answer_txt,
                # tableau
                "documents":   docs,
                "columns":     cols,
                # graphes
                "counts":         res["counts"],
                "byTransmitter":  res["byTransmitter"],
                "bySeverity":     res["bySeverity"],
                "dailyNew":       res["dailyNew"],
                "duration_ms": int((time.time() - start) * 1000)
            }

            
            return clean_jsonable(payload)






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
