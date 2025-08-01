import os
import uuid
import json
import time

from fastapi import FastAPI, Request, HTTPException, APIRouter, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Extra
from starlette.middleware.sessions import SessionMiddleware
from app.db import get_asset_by_id, list_companies
from app.utils.serialize import _deep_clean, clean_jsonable
from app.tools.asset_types import ASSET_TYPE_MAP

from app.agent.orchestrator import handle_query
from app.tools.topology import get_network_topology, topology_to_d3
from typing import List
from app.tools.misconfiguration import detect_misconfig
from app.utils.serialize import extract_columns

app = FastAPI(title="I-CARE Chatbot RAG", version="0.2.0")
api = APIRouter(prefix="/api")

# ── 1. Sessions ───────────────────────────────────────────────────────
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET_KEY", "change_this!"),
    session_cookie="icare_session",
)

# ── 2. CORS (à restreindre en prod) ───────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 3. Schemas Pydantic ───────────────────────────────────────────────
class ChatReq(BaseModel):
    message: str
    locale: str = "fr"

class ChatResp(BaseModel, extra=Extra.allow):
    answer: str
    duration_ms: int | None = None
    # les champs renvoyés par l’orchestrateur (documents, columns…) passeront tels quels

# ── 4. Route /chat ────────────────────────────────────────────────────
@api.post("/chat", response_model=ChatResp)
async def chat(request: Request, payload: ChatReq):
    # (a) récupère ou crée un session_id
    session_id = request.session.get("session_id") or str(uuid.uuid4())
    request.session["session_id"] = session_id

    # démarrage du chrono serveur
    start = time.perf_counter()

    # (b) appelle l’orchestrateur
    resp = await handle_query(payload.message, payload.locale, session_id)

    # calcul du temps écoulé en ms
    elapsed_ms = (time.perf_counter() - start) * 1000
    duration = round(elapsed_ms)

    # (c) uniformise si nécessaire et injecte duration
    if isinstance(resp, str):
        return {"answer": resp, "duration_ms": duration}

    resp["duration_ms"] = duration
    return resp

# ── 5. Route /topology ────────────────────────────────────────────────
@api.get("/topology/{company}")
async def topology(company: str):
    try:
        topo = get_network_topology(company)
        graph = topology_to_d3(topo)
        return {
            "topology": topo,
            "graph": graph
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

# ── 6. Route /assets ──────────────────────────────────────────────────
@api.get("/assets/{client_id}/{asset_id}")
async def asset_detail(client_id: str, asset_id: str):
    """
    Retourne le document complet (nettoyé) de la collection assets
    pour l’ObjectId donné, ou 404 s’il n’existe pas.
    """
    asset = get_asset_by_id(client_id, asset_id)
    if not asset:
        raise HTTPException(404, f"Asset {asset_id} introuvable dans la DB {client_id}")

    # Nettoyage : ObjectId→str, datetime→ISO, on retire _id interne
    cleaned = {}
    for k, v in asset.items():
        if k == "_id":
            continue
        cleaned[k] = _deep_clean(v)

    if "t" in cleaned:
        try:
            raw = int(cleaned["t"])
            label = ASSET_TYPE_MAP.get(raw)
            if label:
                cleaned["t"] = f"{raw} ({label})"
        except Exception:
            pass

    return cleaned

# ── Mono-DB ─────────────────────────────────────────────────────────
@api.get("/misconfig/{company}")
async def misconfig(
    company: str,
    since_days: int = 30
):
    """
    Tasks mal configurées pour une seule base.
    """
    # Appel du helper
    res  = detect_misconfig(company, since_days)
    docs = res["items"]            # déjà aplatis
    for d in docs:
        d["company"] = company
    cols = [
        c for c in [
            'asset_id',
            'err_name',
            'severity',
            'cause',
            'last_acq',
            'freq_err',
            'errcodes'
        ]
        if docs and c in docs[0]
    ]

    return clean_jsonable({
        "counts":        res["counts"],
        "documents":     docs,
        "columns":       cols,
        "byTransmitter": res["byTransmitter"],
        "bySeverity":    res["bySeverity"],
        "dailyNew":      res["dailyNew"],
    })

# ── Multi-DB ────────────────────────────────────────────────────────
@api.get("/misconfig")
async def misconfig_multi(
    client_ids: List[str] = Query(
        None,
        description="Bases à interroger (omit = toutes)"
    ),
    since_days: int = 30
):
    """
    Tasks mal configurées sur plusieurs bases.
    """
    bases = client_ids or list_companies()

    all_items: list[dict] = []
    for comp in sorted(bases, key=str.lower):
        res = detect_misconfig(comp, since_days)
        for item in res["items"]:
            item["company"] = comp
        all_items.extend(res["items"])

    # Réordonner les colonnes pour misconfig multi
    cols = [
        c for c in [
            'company',
            'asset_id',
            'err_name',
            'severity',
            'cause',
            'last_acq',
            'freq_err',
            'errcodes'
        ]
        if all_items and c in all_items[0]
    ]

    return clean_jsonable({
        "documents": all_items,
        "columns":   cols,
        "byTransmitter": res["byTransmitter"],
        "bySeverity":    res["bySeverity"],
        "dailyNew":      res["dailyNew"]
    })

app.include_router(api)
