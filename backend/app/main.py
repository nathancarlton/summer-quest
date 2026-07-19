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
    return {
        "status": "healthy",
        "app": "summer-quest",
        "language": "Python",
        # Render injects RENDER_GIT_COMMIT; compare with `git log` to spot a
        # stale deploy at a glance.
        "commit": os.getenv("RENDER_GIT_COMMIT", "dev")[:7],
    }


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
    p = engine.create_player(body.name.strip(), engine.clean_prefs(body.prefs))
    return engine.public_player(p)


class PrefsBody(BaseModel):
    prefs: dict


@app.post("/api/v1/players/{pid}/prefs")
def update_prefs(pid: str, body: PrefsBody):
    """Merge new favorites into the profile (badge-bonus questions). Keys are
    whitelisted server-side so only the impersonal catalog is stored."""
    p = _player_or_404(pid)
    return engine.public_player(engine.update_prefs(p, body.prefs))


def _player_or_404(pid):
    p = engine.get_player(pid)
    if p is None:
        raise HTTPException(404, "player not found")
    return p


@app.get("/api/v1/players/{pid}")
def get_player(pid: str):
    p = _player_or_404(pid)
    # Opening the app is the earliest signal a quest is coming — start brewing
    # AI questions now so even the FIRST quest of the day can be fresh.
    engine.refill_pool_in_background(p)
    return engine.public_player(p)


@app.get("/api/v1/leaderboard")
def leaderboard():
    return engine.leaderboard()


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


@app.get("/api/v1/expeditions")
def expedition_topics():
    from quest import expeditions
    return [
        {"key": k, "name": name, "emoji": emoji, "desc": desc}
        for k, (name, emoji, desc) in expeditions.TOPICS.items()
    ]


class ExpeditionStart(BaseModel):
    topic: Optional[str] = None  # None = surprise me


@app.post("/api/v1/players/{pid}/expedition")
def start_expedition(pid: str, body: ExpeditionStart = Body(default=ExpeditionStart())):
    p = _player_or_404(pid)
    try:
        return engine.start_expedition(p, body.topic)
    except KeyError:
        raise HTTPException(422, "unknown expedition topic")


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


class ChallengeBody(BaseModel):
    index: int = Field(ge=0, le=50)


@app.post("/api/v1/quests/{qid}/challenge")
def challenge_answer(qid: str, body: ChallengeBody):
    """The learner disputes a ruling — an independent AI appeals judge
    re-evaluates. One challenge per question."""
    quest = _quest_or_404(qid)
    try:
        return engine.challenge_answer(quest, body.index)
    except IndexError:
        raise HTTPException(409, "that question hasn't been answered yet")
    except ValueError as e:
        raise HTTPException(409, str(e))


class ReportBody(BaseModel):
    index: int = Field(ge=0, le=50)
    note: str = Field(default="", max_length=300)


@app.post("/api/v1/quests/{qid}/report")
def report_issue(qid: str, body: ReportBody):
    quest = _quest_or_404(qid)
    p = engine.get_player(quest["player_id"]) or {}
    engine.file_report(p, quest, body.index, "manual", body.note)
    return {"ok": True}


def _require_reports_auth(authorization: str, token: str):
    """Reports contain question text + kids' answers; if SYNC_TOKEN is set,
    require it (header or ?token=). Unset = open, fine for a family app."""
    if config.SYNC_TOKEN and authorization != f"Bearer {config.SYNC_TOKEN}" \
            and token != config.SYNC_TOKEN:
        raise HTTPException(401, "reports require the sync token")


@app.get("/api/v1/reports")
def list_reports(authorization: str = Header(default=""), token: str = ""):
    """Parent view: open this URL in a browser to read flagged questions."""
    _require_reports_auth(authorization, token)
    return engine.get_reports()


@app.delete("/api/v1/reports")
def clear_reports(authorization: str = Header(default=""), token: str = ""):
    _require_reports_auth(authorization, token)
    engine.clear_reports()
    return {"ok": True}


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
