"""Summer Quest API — FastAPI app for Koyeb/Zeabur.

Run locally:   uvicorn backend.app.main:app --reload
In production: the root Procfile boots this on the platform's $PORT.

Env vars (all optional):
  MINIMAX_API_KEY  server-side question generation + short-answer grading
  DATABASE_URL     Postgres for durable storage (else SQLite in data/)
  CORS_ORIGINS     comma-separated allowed origins (else "*")
  SYNC_TOKEN       bearer token required on the CLI sync endpoint
"""
import os
from typing import Optional

from fastapi import Body, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from quest import config

from . import engine

app = FastAPI(title="Summer Quest API", version="1.0.0")

# Lock this down once the Vercel URL exists, e.g.
# CORS_ORIGINS=https://summer-quest.vercel.app,http://localhost:5173
_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class PlayerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    prefs: dict = Field(default_factory=dict)


class QuestStart(BaseModel):
    # The kid's local calendar date, so streaks follow their clock, not UTC.
    local_date: Optional[str] = None


class AnswerBody(BaseModel):
    answer: str = Field(max_length=2000)


@app.get("/")
def health():
    return {"status": "healthy", "app": "summer-quest", "language": "Python"}


@app.get("/api/v1/ai/status")
def ai_status(probe: bool = False):
    """Is MiniMax reachable with the configured key? Feeds the web app's
    status dot; ?probe=true fires a real tiny chat call to check right now."""
    return engine.ai_status(probe)


# ─── Players ─────────────────────────────────────────────────────────────────

@app.get("/api/v1/players")
def list_players():
    """Roster for the device's 'who's playing?' picker — names only, no stats
    leak beyond what the home screen shows anyway."""
    return [
        {"id": p["id"], "name": p["name"], "xp": p["xp"], "streak": p["streak"]}
        for p in engine.list_players()
    ]


@app.post("/api/v1/players", status_code=201)
def create_player(body: PlayerCreate):
    prefs = {k: str(v)[:60] for k, v in body.prefs.items() if k in ("animal", "food", "theme")}
    p = engine.create_player(body.name.strip(), prefs)
    return engine.public_player(p)


def _player_or_404(pid):
    p = engine.get_player(pid)
    if p is None:
        raise HTTPException(404, "player not found")
    return p


@app.get("/api/v1/players/{pid}")
def get_player(pid: str):
    return engine.public_player(_player_or_404(pid))


# Cross-device read per the README's original contract.
@app.get("/api/v1/profile/{pid}")
def get_profile(pid: str):
    return engine.public_player(_player_or_404(pid))


@app.get("/api/v1/players/{pid}/history")
def get_history(pid: str):
    _player_or_404(pid)
    return engine.get_history(pid)


# ─── The quest lifecycle ─────────────────────────────────────────────────────

@app.post("/api/v1/players/{pid}/quest")
def start_quest(pid: str, body: QuestStart = Body(default=QuestStart())):
    p = _player_or_404(pid)
    return engine.start_quest(p, body.local_date)


def _quest_or_404(qid):
    quest = engine.get_quest(qid)
    if quest is None:
        raise HTTPException(404, "quest not found (already completed?)")
    return quest


@app.post("/api/v1/quests/{qid}/answer")
def answer_question(qid: str, body: AnswerBody):
    quest = _quest_or_404(qid)
    try:
        return engine.answer_question(quest, body.answer)
    except IndexError:
        raise HTTPException(409, "all questions already answered")


@app.post("/api/v1/quests/{qid}/complete")
def complete_quest(qid: str):
    quest = _quest_or_404(qid)
    try:
        return engine.complete_quest(quest)
    except ValueError as e:
        raise HTTPException(409, str(e))


# ─── CLI sync (the contract documented in quest/sync.py) ─────────────────────

@app.post("/api/v1/progress")
def cli_progress(payload: dict = Body(...), authorization: str = Header(default="")):
    if config.SYNC_TOKEN and authorization != f"Bearer {config.SYNC_TOKEN}":
        raise HTTPException(401, "bad or missing sync token")
    profile = payload.get("profile") or {}
    try:
        engine.ingest_cli_progress(profile, payload.get("session"))
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True}
