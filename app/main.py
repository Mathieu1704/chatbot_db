import os
import uuid
import json

from fastapi import FastAPI, Request, HTTPException, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Extra
from starlette.middleware.sessions import SessionMiddleware

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

    # (b) appelle l’orchestrateur
    resp = await handle_query(payload.message, payload.locale, session_id)

    # (c) uniformise au besoin
    if isinstance(resp, str):
        return {"answer": resp}

    # resp est déjà un dict complet : on le renvoie tel quel
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

app.include_router(api)
