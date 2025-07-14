import os, uuid, json
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Extra
from starlette.middleware.sessions import SessionMiddleware

from app.agent.orchestrator import handle_query

app = FastAPI(title="I-CARE Chatbot RAG", version="0.2.0")

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

class ChatResp(BaseModel, extra=Extra.allow):   # ← autorise les clés supplémentaires
    answer: str
    duration_ms: int | None = None
    # les champs renvoyés par l’orchestrateur (documents, columns…) passeront tels quels

# ── 4. Route /chat ────────────────────────────────────────────────────
@app.post("/chat", response_model=ChatResp)
async def chat(request: Request, payload: ChatReq):
    # (a) récupère ou crée un session_id
    session_id = request.session.get("session_id") or str(uuid.uuid4())
    request.session["session_id"] = session_id

    # (b) appelle l’orchestrateur
    resp = await handle_query(payload.message, payload.locale, session_id)

    # (c) uniformise au besoin
    if isinstance(resp, str):
        return {"answer": resp}                # pas de docs → juste la phrase

    # resp est déjà un dict complet : on le renvoie tel quel
    return resp
