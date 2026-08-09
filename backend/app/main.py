"""Summer Quest API — FastAPI app for Render (or any Heroku-style host).

Run locally:   uvicorn backend.app.main:app --reload
In production: the root Procfile boots this on the platform's $PORT.

Env vars (all optional):
  MINIMAX_API_KEY  server-side question generation + short-answer grading
  DATABASE_URL     Postgres for durable storage (else SQLite in data/)
  CORS_ORIGINS     comma-separated allowed origins (else "*")
  SYNC_TOKEN       bearer token for CLI sync, reports, and password resets

Auth model: players set a secret password (+ a hint only they understand).
Logging in issues an opaque bearer token sent as X-Player-Token; every
player-scoped endpoint requires it once the player has a secret. Players
WITHOUT a secret yet (brand-new via CLI import, or pre-auth profiles) are
accessible without a token — the web app forces secret creation at login,
which closes that door. Rate limits protect password guessing and the
endpoints that spend MiniMax credits.
"""
import os
import time
from typing import Optional

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from quest import config

from . import engine, security, voice

app = FastAPI(title="Summer Quest API", version="1.1.0")
app.include_router(voice.router)

# Lock this down once the Vercel URL exists, e.g.
# CORS_ORIGINS=https://summer-quest.vercel.app,http://localhost:5173
_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins or ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def global_rate_limit(request: Request, call_next):
    if request.method != "OPTIONS":  # never throttle CORS preflights
        try:
            security.limiter.check(
                f"global:{security.client_ip(request)}", 240, 60
            )
        except HTTPException as e:
            return JSONResponse(status_code=e.status_code,
                                content={"detail": e.detail})
    start = time.perf_counter()
    response = await call_next(request)
    # Server-side handling time, visible in browser devtools — separates
    # "the backend is slow" from "the network/wake-up is slow" at a glance.
    response.headers["X-Process-Time"] = f"{(time.perf_counter() - start) * 1000:.0f}ms"
    return response


# ─── Auth helpers ────────────────────────────────────────────────────────────

def _player_or_404(pid):
    p = engine.get_player(pid)
    if p is None:
        raise HTTPException(404, "player not found")
    return p


def _authed_player(pid, token):
    """Load the player, enforcing the token once they have a secret set.
    Secret-less players (CLI imports, pre-auth profiles) pass through — the
    web app forces them to create a secret at login. One player read + one
    token read; the generation check runs against the already-loaded player
    (answer latency lives and dies by store round trips)."""
    p = _player_or_404(pid)
    if p.get("secret_hash"):
        rec = engine.token_record(token)
        if not rec or rec.get("pid") != pid \
                or rec.get("gen") != p.get("auth_gen", 0):
            raise HTTPException(401, "login required")
    return p


def _authed_quest(qid, token):
    """Returns (quest, player) so handlers can pass the already-loaded
    player into the engine instead of re-reading it."""
    quest = engine.get_quest(qid)
    if quest is None:
        raise HTTPException(404, "quest not found (already completed?)")
    player = _authed_player(quest["player_id"], token)
    return quest, player


def _any_valid_token(token):
    if engine.player_for_token(token) is None:
        raise HTTPException(401, "login required")


# ─── Health + AI status ──────────────────────────────────────────────────────

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
def ai_status(probe: bool = False, request: Request = None,
              x_player_token: str = Header(default="")):
    """Is MiniMax reachable with the configured key? Feeds the web app's
    status dot. ?probe=true fires a real chat call, so it needs a login and
    is rate-limited — otherwise strangers could spend MiniMax credits."""
    if probe:
        _any_valid_token(x_player_token)
        security.limiter.check(
            f"probe:{security.client_ip(request)}", 6, 3600
        )
    return engine.ai_status(probe)


# ─── Players + login ─────────────────────────────────────────────────────────

@app.get("/api/v1/players")
def list_players():
    """Roster for the login screen: names + whether a secret exists. No
    stats — this endpoint is pre-auth by necessity."""
    return [
        {"id": p["id"], "name": p["name"],
         "has_secret": bool(p.get("secret_hash"))}
        for p in engine.list_players()
    ]


class PlayerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    prefs: dict = Field(default_factory=dict)
    secret: str = Field(min_length=4, max_length=64)
    hint: str = Field(min_length=3, max_length=100)


@app.post("/api/v1/players", status_code=201,
          dependencies=[Depends(security.rate_limit("create", 5, 3600))])
def create_player(body: PlayerCreate):
    """Brand-new players choose their secret password + hint up front."""
    p = engine.create_player(body.name.strip(), engine.clean_prefs(body.prefs))
    engine.set_secret(p, body.secret, body.hint)
    return {"token": engine.issue_token(p), "player": engine.public_player(p)}


class LoginBody(BaseModel):
    secret: str = Field(min_length=1, max_length=64)


@app.post("/api/v1/players/{pid}/login")
def login(pid: str, body: LoginBody, request: Request):
    # Tight per-player+IP limit: 5 guesses a minute stops brute force cold.
    security.limiter.check(
        f"login:{security.client_ip(request)}:{pid}", 5, 60
    )
    p = _player_or_404(pid)
    if not p.get("secret_hash"):
        raise HTTPException(409, "no secret set yet — create one first")
    if not security.verify_secret(body.secret, p["secret_hash"]):
        engine.log_activity(p, "login_failed")
        raise HTTPException(401, "wrong secret password")
    engine.log_activity(p, "login")
    return {"token": engine.issue_token(p), "player": engine.public_player(p)}


@app.post("/api/v1/players/{pid}/logout")
def logout(pid: str, x_player_token: str = Header(default="")):
    """Signing out ends the session in the parent view and kills this
    device's token; other devices stay signed in."""
    p = _authed_player(pid, x_player_token)
    engine.revoke_token(x_player_token)
    engine.log_activity(p, "logout")
    return {"ok": True}


class NameBody(BaseModel):
    name: str = Field(min_length=1, max_length=40)


@app.post("/api/v1/players/{pid}/name",
          dependencies=[Depends(security.rate_limit("rename", 6, 3600))])
def rename_player(pid: str, body: NameBody,
                  x_player_token: str = Header(default="")):
    """Change your display name (home screen, leaderboard, parent view).
    Only the logged-in owner can do it; names stay unique in the family."""
    p = _authed_player(pid, x_player_token)
    try:
        return engine.public_player(engine.rename_player(p, body.name))
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.get("/api/v1/players/{pid}/hint")
def get_hint(pid: str,
             _=Depends(security.rate_limit("hint", 20, 3600))):
    """The hint is shown to help its owner remember — semi-public by design,
    which is why the create-secret flow insists on hints only the kid can
    interpret."""
    p = _player_or_404(pid)
    return {"hint": p.get("secret_hint", "")}


class SecretBody(BaseModel):
    secret: str = Field(min_length=4, max_length=64)
    hint: str = Field(min_length=3, max_length=100)


@app.post("/api/v1/players/{pid}/secret",
          dependencies=[Depends(security.rate_limit("setsecret", 10, 3600))])
def set_secret(pid: str, body: SecretBody,
               x_player_token: str = Header(default="")):
    """First-time creation for players without a secret (CLI imports,
    pre-auth profiles); changing an existing secret requires being logged in."""
    p = _player_or_404(pid)
    existing = bool(p.get("secret_hash"))
    if existing:
        tp = engine.player_for_token(x_player_token)
        if not tp or tp["id"] != pid:
            raise HTTPException(401, "login required to change your secret")
    engine.set_secret(p, body.secret, body.hint)
    engine.log_activity(p, "secret_changed" if existing else "secret_created")
    return {"token": engine.issue_token(p), "player": engine.public_player(p)}


@app.post("/api/v1/players/{pid}/merge")
def merge_profiles(pid: str, x_player_token: str = Header(default="")):
    """Accept a pending combine-profiles offer (set on the player record by
    a parent). Only the logged-in owner of the profile can accept."""
    tp = engine.player_for_token(x_player_token)
    if not tp or tp["id"] != pid:
        raise HTTPException(401, "login required")
    try:
        return engine.accept_merge(tp)
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/api/v1/players/{pid}/lockout",
          dependencies=[Depends(security.rate_limit("lockout", 3, 3600))])
def lockout(pid: str):
    """'I forgot my secret password' — notifies the game developers via the
    reports queue so a grown-up can reset it."""
    p = _player_or_404(pid)
    engine.file_simple_report(
        p, "locked_out",
        "This learner can't log in and asked for a password reset. "
        f"Reset with: POST /api/v1/players/{p['id']}/secret/reset "
        "(Bearer SYNC_TOKEN when set).",
    )
    return {"ok": True,
            "message": "The game developers have been notified — ask your grown-up!"}


@app.post("/api/v1/players/{pid}/secret/reset")
def reset_secret(pid: str, authorization: str = Header(default=""), token: str = ""):
    """Parent-side reset: clears the secret (and all tokens) so the kid
    creates a new one at next login. Gated by SYNC_TOKEN when set."""
    _require_reports_auth(authorization, token)
    engine.clear_secret(_player_or_404(pid))
    return {"ok": True}


class PrefsBody(BaseModel):
    prefs: dict


@app.post("/api/v1/players/{pid}/prefs")
def update_prefs(pid: str, body: PrefsBody,
                 x_player_token: str = Header(default="")):
    """Merge new favorites into the profile (badge-bonus questions). Keys are
    whitelisted server-side so only the impersonal catalog is stored."""
    p = _authed_player(pid, x_player_token)
    return engine.public_player(engine.update_prefs(p, body.prefs))


@app.get("/api/v1/players/{pid}")
def get_player(pid: str, x_player_token: str = Header(default="")):
    p = _authed_player(pid, x_player_token)
    # Opening the app is the earliest signal a quest is coming — start brewing
    # AI questions now so even the FIRST quest of the day can be fresh.
    engine.refill_pool_in_background(p)
    engine.touch_seen(p)  # throttled internally; no write on most calls
    return engine.public_player(p)


@app.get("/api/v1/leaderboard")
def leaderboard(x_player_token: str = Header(default="")):
    _any_valid_token(x_player_token)
    return engine.leaderboard()


# Cross-device read per the README's original contract.
@app.get("/api/v1/profile/{pid}")
def get_profile(pid: str, x_player_token: str = Header(default="")):
    return engine.public_player(_authed_player(pid, x_player_token))


@app.get("/api/v1/players/{pid}/active")
def get_active(pid: str, x_player_token: str = Header(default="")):
    """Is there an unfinished session? Powers the home screen's forced
    'Finish your quest!' button — there's no fresh-start path around it."""
    p = _authed_player(pid, x_player_token)
    quest = engine.active_quest(p)
    if not quest:
        return {"active": False}
    return {
        "active": True,
        "kind": quest.get("kind", "quest"),
        "answered": len(quest["results"]),
        "total": len(quest["questions"]),
    }


@app.get("/api/v1/players/{pid}/history")
def get_history(pid: str, x_player_token: str = Header(default="")):
    _authed_player(pid, x_player_token)
    return engine.get_history(pid)


# ─── The quest lifecycle ─────────────────────────────────────────────────────

class QuestStart(BaseModel):
    # The kid's local calendar date, so streaks follow their clock, not UTC.
    local_date: Optional[str] = None


@app.post("/api/v1/players/{pid}/quest",
          dependencies=[Depends(security.rate_limit("start", 30, 3600))])
def start_quest(pid: str, body: QuestStart = Body(default=QuestStart()),
                x_player_token: str = Header(default="")):
    p = _authed_player(pid, x_player_token)
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


@app.post("/api/v1/players/{pid}/expedition",
          dependencies=[Depends(security.rate_limit("start", 30, 3600))])
def start_expedition(pid: str,
                     body: ExpeditionStart = Body(default=ExpeditionStart()),
                     x_player_token: str = Header(default="")):
    p = _authed_player(pid, x_player_token)
    try:
        return engine.start_expedition(p, body.topic)
    except KeyError:
        raise HTTPException(422, "unknown expedition topic")


# ─── Reading Room ────────────────────────────────────────────────────────────

@app.get("/api/v1/players/{pid}/books")
def list_books(pid: str, x_player_token: str = Header(default="")):
    """The bookshelf: catalog + this player's per-book progress. Chapter
    counts appear once a book has been fetched (first open) — showing null
    beforehand avoids downloading all eight books just to draw the shelf."""
    from . import books
    p = _authed_player(pid, x_player_token)
    out = []
    for key, info in books.BOOKS.items():
        meta = books.get_meta(key)
        prog = engine.reading_progress(p, key)
        out.append({
            "key": key, "title": info["title"], "author": info["author"],
            "emoji": info["emoji"],
            "chapters": meta["chapters"] if meta else None,
            "finished_through": prog["finished"],
            "quizzed_count": len(prog["quizzed"]),
        })
    return out


@app.get("/api/v1/players/{pid}/book/{book}/chapter/{chapter}",
         dependencies=[Depends(security.rate_limit("chapter", 120, 3600))])
def read_chapter(pid: str, book: str, chapter: int,
                 x_player_token: str = Header(default="")):
    p = _authed_player(pid, x_player_token)
    try:
        return engine.open_chapter(p, book, chapter)
    except KeyError:
        raise HTTPException(404, "unknown book")
    except IndexError:
        raise HTTPException(404, "no such chapter")
    except Exception as e:
        raise HTTPException(502, f"couldn't fetch the book right now: {e}")


@app.post("/api/v1/players/{pid}/book/{book}/chapter/{chapter}/finish")
def finish_chapter(pid: str, book: str, chapter: int,
                   x_player_token: str = Header(default="")):
    p = _authed_player(pid, x_player_token)
    if book not in engine.books.BOOKS:
        raise HTTPException(404, "unknown book")
    return engine.finish_chapter(p, book, chapter)


@app.post("/api/v1/players/{pid}/book/{book}/chapter/{chapter}/quiz",
          dependencies=[Depends(security.rate_limit("start", 30, 3600))])
def start_reading_quiz(pid: str, book: str, chapter: int,
                       x_player_token: str = Header(default="")):
    p = _authed_player(pid, x_player_token)
    try:
        return engine.start_reading_quiz(p, book, chapter)
    except KeyError:
        raise HTTPException(404, "unknown book")
    except engine.QuizNotReady:
        raise HTTPException(
            425, "The quiz for this chapter is still being written — "
                 "keep reading and try again in a minute!"
        )


class AnswerBody(BaseModel):
    answer: str = Field(default="", max_length=2000)
    timed_out: bool = False


@app.post("/api/v1/quests/{qid}/answer")
def answer_question(qid: str, body: AnswerBody,
                    x_player_token: str = Header(default="")):
    quest, player = _authed_quest(qid, x_player_token)
    try:
        return engine.answer_question(quest, body.answer, body.timed_out, player)
    except IndexError:
        raise HTTPException(409, "all questions already answered")


@app.post("/api/v1/quests/{qid}/complete")
def complete_quest(qid: str, x_player_token: str = Header(default="")):
    quest, player = _authed_quest(qid, x_player_token)
    try:
        return engine.complete_quest(quest, player)
    except ValueError as e:
        raise HTTPException(409, str(e))


class ChallengeBody(BaseModel):
    index: int = Field(ge=0, le=50)


@app.post("/api/v1/quests/{qid}/challenge",
          dependencies=[Depends(security.rate_limit("challenge", 20, 3600))])
def challenge_answer(qid: str, body: ChallengeBody,
                     x_player_token: str = Header(default="")):
    """The learner disputes a ruling — an independent AI appeals judge
    re-evaluates. One challenge per question."""
    quest, player = _authed_quest(qid, x_player_token)
    try:
        return engine.challenge_answer(quest, body.index, player)
    except IndexError:
        raise HTTPException(409, "that question hasn't been answered yet")
    except ValueError as e:
        raise HTTPException(409, str(e))


class ReportBody(BaseModel):
    index: int = Field(ge=0, le=50)
    note: str = Field(default="", max_length=300)


@app.post("/api/v1/quests/{qid}/report",
          dependencies=[Depends(security.rate_limit("report", 20, 3600))])
def report_issue(qid: str, body: ReportBody,
                 x_player_token: str = Header(default="")):
    quest, player = _authed_quest(qid, x_player_token)
    engine.file_report(player, quest, body.index, "manual", body.note)
    engine.log_activity(player, "reported_question")
    # A reported question is pulled from EVERYONE's rotation until a parent
    # reviews it in the Parent Zone.
    q = quest["questions"][body.index] if body.index < len(quest["questions"]) else None
    if q and q.get("id"):
        engine.block_question(q["id"], "reported", q.get("question", ""))
    return {"ok": True}


# ─── Reports (parent view) ───────────────────────────────────────────────────

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


@app.get("/api/v1/activity")
def activity(authorization: str = Header(default=""), token: str = "",
             days: int = 14):
    """Parent view: who signed in when, what they did, when they left.
    Same SYNC_TOKEN gate as reports — it's a window on the kids' sessions."""
    _require_reports_auth(authorization, token)
    return engine.activity_overview(max(1, min(days, 90)))


@app.delete("/api/v1/reports")
def clear_reports(authorization: str = Header(default=""), token: str = ""):
    _require_reports_auth(authorization, token)
    engine.clear_reports()
    return {"ok": True}


class UnblockBody(BaseModel):
    id: str = Field(min_length=1, max_length=64)


@app.post("/api/v1/questions/unblock")
def unblock_question(body: UnblockBody, authorization: str = Header(default=""),
                     token: str = ""):
    """Parent review outcome: the question was actually fine — put it back
    into everyone's rotation."""
    _require_reports_auth(authorization, token)
    return {"ok": True, "unblocked": engine.unblock_question(body.id)}


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
