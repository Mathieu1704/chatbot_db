import os
import uuid
import json
import time

from fastapi import FastAPI, Request, HTTPException, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Extra
from starlette.middleware.sessions import SessionMiddleware
from app.db import get_asset_by_id
from app.utils.serialize import _deep_clean
from app.tools.asset_types import ASSET_TYPE_MAP

from app.agent.orchestrator import handle_query
from app.tools.topology import get_network_topology, topology_to_d3

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

app.include_router(api)
