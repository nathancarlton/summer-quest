"""Server-side game engine — the CLI's daily-quest loop, re-cut for HTTP.

Reuses the quest package verbatim: ai.py for MiniMax generation/grading,
bank.py for the offline pack + validation + no-repeat ids, profile.py for
badges/levels, config.py for constants. What changes is where state lives
(the kv store instead of local JSON files) and that the question pool is
per player instead of per machine.

Answers never leave the server: the client gets sanitized questions and
posts answers back one at a time for grading, so the browser can't peek.
"""
import hashlib
import math
import random
import re
import threading
import uuid
from datetime import date, datetime, timedelta, timezone

from quest import ai, bank, config, expeditions, profile as profile_mod

from . import books, security, storage

POOL_TARGET = 2    # ready-made themed quest sessions to keep queued per player
EXPOOL_TARGET = 2  # ready-made expeditions queued per player (brewed AFTER quests)
EXPEDITION_SIZE = 5
SPARKS_PER_CORRECT = 10  # expeditions pay Sparks, a separate counter from XP

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ─── Players ─────────────────────────────────────────────────────────────────

def _player_key(pid):
    return f"player:{pid}"


def get_player(pid):
    return storage.get_json(_player_key(pid))


def save_player(p):
    storage.set_json(_player_key(p["id"]), p)


def create_player(name, prefs):
    p = profile_mod._default(name)
    p["prefs"] = prefs or {}
    save_player(p)
    log_activity(p, "joined", {"name": name})
    # Start brewing AI questions immediately — by the time the kid finishes
    # looking at the home screen, their first quest may already be AI-fresh.
    refill_pool_in_background(p)
    return p


def list_players():
    out = []
    for key in storage.store.keys("player:"):
        p = storage.get_json(key)
        if p:
            out.append(p)
    out.sort(key=lambda p: p.get("name", "").lower())
    return out


def leaderboard():
    """Family standings, ranked by XP. Ties break alphabetically."""
    rows = []
    for p in list_players():
        p = _normalize(p)
        num, title, _ = profile_mod.level_info(p["xp"])
        rows.append({
            "id": p["id"],
            "name": p["name"],
            "xp": p["xp"],
            "streak": p["streak"],
            "level_num": num,
            "level_title": title,
            "badges": len(p["badges"]),
            "sparks": p.get("sparks", 0),
            "stickers": sum(p.get("stickers", {}).values()),
            "sessions": p.get("sessions_completed", 0),
            "last_played": p.get("last_played"),
        })
    rows.sort(key=lambda r: (-r["xp"], r["name"].lower()))
    return rows


def _normalize(p):
    """Same forward-compat defaults profile.load() applies to old files."""
    for c in config.CATEGORIES:
        p["categories"].setdefault(c, {"answered": 0, "correct": 0})
    p.setdefault("sessions_completed", 0)
    p.setdefault("offline", {"mastered": [], "review": []})
    p.setdefault("prefs", {})
    p.setdefault("difficulty", 2)
    p.setdefault("sparks", 0)
    p.setdefault("stickers", {})
    p.setdefault("active_quest", None)
    p.setdefault("subtopics", {})
    # Reading Room: per book, chapters finished + which chapters were quizzed.
    p.setdefault("reading", {})
    return p


# Favorites are deliberately impersonal — things, places, weather; never
# people. Keys must match ai._PREF_PHRASES and the web app's badge-bonus
# question catalog.
PREF_KEYS = ("animal", "food", "theme", "color", "place", "instrument",
             "sport", "song", "weather")


def clean_prefs(raw):
    out = {}
    for k, v in (raw or {}).items():
        if k in PREF_KEYS and isinstance(v, (str, int, float)):
            v = str(v).strip()[:60]
            if v:
                out[k] = v
    return out


def update_prefs(p, new_prefs):
    """Merge favorite changes; an empty value REMOVES that favorite — so a
    kid can retire a panther era entirely, not just overwrite it."""
    prefs = p.setdefault("prefs", {})
    for k, v in (new_prefs or {}).items():
        if k not in PREF_KEYS or not isinstance(v, (str, int, float)):
            continue
        v = str(v).strip()[:60]
        if v:
            prefs[k] = v
        else:
            prefs.pop(k, None)
    save_player(p)
    log_activity(p, "favorites", {"changed": sorted(new_prefs or {})})
    return p


def rename_player(p, new_name):
    """Change the name shown everywhere (home screen, leaderboard, parent
    view). Names must stay distinct within the family — the login roster
    shows names only, so two Sams would be indistinguishable there."""
    name = " ".join(str(new_name).split())[:40]
    if not name:
        raise ValueError("a name can't be blank")
    old = p.get("name", "")
    if name == old:
        return p
    if name.lower() != old.lower():
        for other in list_players():
            if other["id"] != p["id"] and other.get("name", "").lower() == name.lower():
                raise ValueError(f"{name} is already taken by another player")
    p["name"] = name
    # Marks the web name as authoritative so a later CLI sync (whose profile
    # still carries the old name) can't silently rename them back.
    p["renamed_at"] = datetime.now(timezone.utc).isoformat()
    save_player(p)
    log_activity(p, "renamed", {"from": old, "to": name})
    return p


def public_player(p):
    """Profile + everything the frontend needs pre-computed (level, badges,
    active-session state — bundled here so the home screen renders the right
    call-to-action in one fetch, with no start/resume button flicker).
    Auth internals are stripped; only a has_secret flag goes out."""
    p = _normalize(dict(p))
    p["has_secret"] = bool(p.pop("secret_hash", None))
    p.pop("secret_hint", None)
    p.pop("auth_gen", None)
    p.pop("merge_offer", None)  # surfaces only via the quest-complete payload
    quest = active_quest(p)
    p["active_info"] = (
        {"active": True, "kind": quest.get("kind", "quest"),
         "answered": len(quest["results"]), "total": len(quest["questions"])}
        if quest else {"active": False}
    )
    num, title, nxt = profile_mod.level_info(p["xp"])
    p["level"] = {
        "num": num,
        "title": title,
        "next": {"threshold": nxt[0], "title": nxt[1]} if nxt else None,
    }
    p["badge_details"] = [
        {"key": b, "label": profile_mod.BADGES[b][0], "desc": profile_mod.BADGES[b][1]}
        for b in p["badges"]
        if b in profile_mod.BADGES
    ]
    return p


# ─── Secrets + auth tokens ───────────────────────────────────────────────────

def set_secret(p, secret, hint):
    """Set (or change) a player's secret password + hint, invalidating any
    previously issued tokens via the auth generation counter."""
    p["secret_hash"] = security.hash_secret(secret)
    p["secret_hint"] = str(hint).strip()[:100]
    p["auth_gen"] = p.get("auth_gen", 0) + 1
    save_player(p)


def clear_secret(p):
    """Parent reset: the kid re-creates their secret on next login."""
    p.pop("secret_hash", None)
    p.pop("secret_hint", None)
    p["auth_gen"] = p.get("auth_gen", 0) + 1
    save_player(p)


def issue_token(p):
    token = security.new_token()
    storage.set_json(security.token_key(token), {
        "pid": p["id"], "gen": p.get("auth_gen", 0),
    })
    return token


def token_record(token):
    """Raw token record ({pid, gen}) or None — lets callers who already
    hold the player validate without a second player read."""
    if not token:
        return None
    return storage.get_json(security.token_key(token))


def player_for_token(token):
    """Resolve a bearer token to its player, or None. Tokens die when the
    secret changes or is reset (generation mismatch)."""
    rec = token_record(token)
    if not rec:
        return None
    p = get_player(rec.get("pid"))
    if p is None or rec.get("gen") != p.get("auth_gen", 0):
        return None
    return p


def revoke_token(token):
    """Signing out: drop this one token. Other devices stay logged in (only
    a secret change invalidates every token at once)."""
    if token:
        storage.store.delete(security.token_key(token))


# ─── Streaks (client-local dates) ────────────────────────────────────────────

def _update_streak(p, today):
    """profile.update_streak, but on the KID'S local date (sent by the client)
    rather than the server clock — a quest at 9pm in Minnesota shouldn't count
    for tomorrow just because the server runs in UTC."""
    if p["last_played"] == today:
        return False
    yesterday = (date.fromisoformat(today) - timedelta(days=1)).isoformat()
    p["streak"] = p["streak"] + 1 if p["last_played"] == yesterday else 1
    p["last_played"] = today
    return True


def _client_date(local_date):
    if local_date and _DATE_RE.match(local_date):
        return local_date
    return date.today().isoformat()


# ─── Global question blocklist + shared bank ────────────────────────────────
# Question ids are content-hashed, so blocking/sharing works across players.

BLOCKED_KEY = "blocked_questions"
MAX_BLOCKED = 500


def blocked_ids():
    return set(storage.get_json(BLOCKED_KEY, {}).keys())


def block_question(qid, reason, text=""):
    """A challenged-and-overturned or reported question is pulled from
    EVERYONE's rotation until a parent restores it in the Parent Zone."""
    blocked = storage.get_json(BLOCKED_KEY, {})
    blocked[qid] = {"reason": reason, "text": str(text)[:200],
                    "ts": datetime.now(timezone.utc).isoformat()}
    if len(blocked) > MAX_BLOCKED:
        oldest = sorted(blocked.items(), key=lambda kv: kv[1].get("ts", ""))
        blocked = dict(oldest[len(blocked) - MAX_BLOCKED:])
    storage.set_json(BLOCKED_KEY, blocked)


def unblock_question(qid):
    blocked = storage.get_json(BLOCKED_KEY, {})
    if blocked.pop(qid, None) is not None:
        storage.set_json(BLOCKED_KEY, blocked)
        return True
    return False


SHARED_LA_KEY = "shared_bank:la"
SHARED_MATH_KEY = "shared_bank:math"
MAX_SHARED = 300


def _shared_key_for(q):
    if q.get("category") in expeditions.TOPICS:
        return f"shared_bank:x:{q['category']}"
    if q.get("category") == "math_challenge":
        return SHARED_MATH_KEY
    return SHARED_LA_KEY


def share_questions(qs):
    """Audited AI questions join the communal bank so every player benefits
    from questions any one player's brewing produced (and paid for)."""
    by_key = {}
    for q in qs:
        if q.get("id"):
            by_key.setdefault(_shared_key_for(q), []).append(q)
    for key, batch in by_key.items():
        bank_qs = storage.get_json(key, [])
        known = {b.get("id") for b in bank_qs}
        bank_qs.extend(q for q in batch if q["id"] not in known)
        storage.set_json(key, bank_qs[-MAX_SHARED:])


def shared_sample(key, n, exclude):
    """Fresh communal questions for a top-up: not mastered, not blocked."""
    pool = [q for q in storage.get_json(key, []) if q.get("id") not in exclude]
    random.shuffle(pool)
    return pool[:n]


# ─── Question selection (mirrors session.py) ────────────────────────────────

def _build_mix(n):
    la_count = round(n * config.LA_RATIO)
    return la_count, n - la_count


def _finalize(p, questions, n, la_count):
    """No repeats from ANY source: drop mastered/duplicate/globally-blocked
    questions by content-hash id, top back up from the shared communal bank
    first (AI questions other players' brewing produced), then the curated
    bank, and guarantee option letters."""
    off = p["offline"]
    mastered = set(off["mastered"])
    blocked = blocked_ids()
    used, result = set(), []
    for q in questions:
        qid = q.get("id") or bank.question_id(q)
        q["id"] = qid
        if qid in mastered or qid in used or qid in blocked:
            continue
        used.add(qid)
        result.append(q)
    if len(result) < n:
        exclude = mastered | used | blocked
        communal = (shared_sample(SHARED_LA_KEY, n, exclude)
                    + shared_sample(SHARED_MATH_KEY, n, exclude))
        random.shuffle(communal)
        for q in communal[: n - len(result)]:
            used.add(q["id"])
            result.append(q)
    if len(result) < n:
        for q in bank.sample(n - len(result), la_count, mastered | used | blocked,
                             off["review"],
                             subtopic_plan=profile_mod.subtopic_plan(p)):
            if q["id"] not in used and q["id"] not in blocked:
                used.add(q["id"])
                result.append(q)
    return [bank.ensure_option_letters(q) for q in result[:n]]


def _offline_raw(p, prefs, n, la_count):
    # Personalized template questions are an occasional cameo (one, half the
    # time), not the opening act of every session — favorites are spice.
    extras = []
    if random.random() < 0.5:
        extras = [q for q in bank.personalized(prefs) if bank.valid_question(q)]
        random.shuffle(extras)
        extras = extras[:1]
    off = p["offline"]
    filler = bank.sample(n - len(extras), la_count, off["mastered"], off["review"],
                         subtopic_plan=profile_mod.subtopic_plan(p))
    return extras + filler


def _fetch_questions(p, n):
    la_count, _ = _build_mix(n)
    prefs = p.get("prefs") or {}

    pooled = _pool_take(p["id"])
    if pooled:
        valid = [q for q in pooled if bank.valid_question(q)]
        if len(valid) >= max(3, n // 2):
            return _finalize(p, valid, n, la_count)
    return _finalize(p, _offline_raw(p, prefs, n, la_count), n, la_count)


def sanitize_question(q):
    """What the browser is allowed to see — no answer, no explanation."""
    return {
        "id": q["id"],
        "category": q["category"],
        "type": q["type"],
        "question": q["question"],
        "passage": q.get("passage"),
        "options": q.get("options"),
    }


# ─── AI health (feeds the parent-facing status dot in the web app) ──────────

_ai_status = {
    "state": "unknown",  # unknown | ok | error (no_key handled in ai_status)
    "detail": "no AI call made since the server last started",
    "checked": None,
}


def _note_ai(ok, detail=""):
    _ai_status["state"] = "ok" if ok else "error"
    _ai_status["detail"] = str(detail)[:300]
    _ai_status["checked"] = datetime.now(timezone.utc).isoformat()


def ai_status(probe=False):
    """Health of the MiniMax connection. Normally reports the outcome of the
    most recent organic call (generation or grading); `probe` fires a real,
    tiny chat request right now — the definitive is-the-key-valid check."""
    if not config.MINIMAX_API_KEY:
        return {
            "configured": False,
            "state": "no_key",
            "detail": "MINIMAX_API_KEY is not set on the server",
            "checked": None,
            "model": config.MINIMAX_MODEL,
        }
    if probe:
        try:
            ai._chat(
                [{"role": "user", "content": "Reply with the single word: OK"}],
                temperature=0.0,
                max_tokens=500,
            )
            _note_ai(True, "probe succeeded")
        except Exception as e:
            _note_ai(False, f"probe failed: {e}")
    return {"configured": True, "model": config.MINIMAX_MODEL, **_ai_status}


# ─── Per-player question pool + background refill ───────────────────────────

def _pool_key(pid):
    return f"pool:{pid}"


def _pool_take(pid):
    """Serve gate: ONLY sessions that passed the adversarial audit
    (verified flag) are ever handed to a learner. Unverified entries —
    e.g. brewed before the audit existed — stay queued for the sweeper,
    and the caller falls back to the curated offline bank meanwhile."""
    sessions = storage.get_json(_pool_key(pid), [])
    for i, s in enumerate(sessions):
        if s.get("verified"):
            sessions.pop(i)
            storage.set_json(_pool_key(pid), sessions)
            return s.get("questions", [])
    return None


def _pool_count(pid):
    return len(storage.get_json(_pool_key(pid), []))


def _session_fingerprint(s):
    """Stable identity for a stored pool entry, so the sweeper can write back
    audit results without resurrecting a session a kid took mid-audit."""
    qs = s.get("questions") or []
    basis = (s.get("theme") or s.get("topic") or "") + "|" + (
        qs[0].get("question", "") if qs else ""
    )
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]


def _audit_pools(pid):
    """Sweep unverified pool entries (brewed before the serve gate existed):
    drop confused questions, run the adversarial answer-key audit, and mark
    the survivors verified so the serve gate lets them through. Runs inside
    the refill worker, before any new generation."""
    for key in (_pool_key(pid), _expool_key(pid)):
        snapshot = storage.get_json(key, [])
        for s in snapshot:
            if s.get("verified"):
                continue
            fp = _session_fingerprint(s)
            qs = [q for q in s.get("questions", []) if not ai.looks_confused(q)]
            try:
                qs = ai.verify_mc(qs)
                _note_ai(True, "pool audit succeeded")
            except Exception as e:
                _note_ai(False, f"pool audit failed: {e}")
                return  # AI unreachable — leave for the next sweep
            # Re-read before writing: only update the entry if it's still there.
            current = storage.get_json(key, [])
            changed = False
            for entry in current:
                if not entry.get("verified") and _session_fingerprint(entry) == fp:
                    entry["questions"] = qs
                    entry["verified"] = True
                    changed = True
                    break
            if changed:
                # Too few survivors = a rotten session; drop it entirely.
                current = [e for e in current
                           if not (e.get("verified") and len(e.get("questions", [])) < 3)]
                storage.set_json(key, current)


_refilling = set()
_refill_lock = threading.Lock()


def _background_work_pending(pid):
    """Anything for the worker to do? Unaudited entries to sweep, or either
    pool short of VERIFIED (servable) sessions. Counting raw entries would
    deadlock: a pool full of unverified sessions would look 'full' and the
    sweeper would never run."""
    pool = storage.get_json(_pool_key(pid), [])
    ex = storage.get_json(_expool_key(pid), [])
    if any(not s.get("verified") for s in pool + ex):
        return True
    if sum(1 for s in pool if s.get("verified")) < POOL_TARGET:
        return True
    return sum(1 for s in ex if s.get("verified")) < EXPOOL_TARGET


def refill_pool_in_background(p):
    """Audit anything unswept, then brew the next themed sessions while the
    kid plays. No-op without an API key, if a worker for this player is
    already running, or if there's nothing to do."""
    pid = p["id"]
    if not config.MINIMAX_API_KEY:
        return
    with _refill_lock:
        if pid in _refilling or not _background_work_pending(pid):
            return
        _refilling.add(pid)

    la_count, math_count = _build_mix(config.QUESTIONS_PER_SESSION)
    weak = profile_mod.weak_categories(p)
    prefs = p.get("prefs") or {}
    difficulty = p.get("difficulty", 2)
    subtopic_plan = profile_mod.subtopic_plan(p)

    def _worker():
        try:
            # Audit anything already queued that predates the serve gate,
            # so it becomes servable again instead of sitting dead.
            _audit_pools(pid)
            threshold = max(3, (la_count + math_count) // 2)
            while _pool_count(pid) < POOL_TARGET:
                theme = random.choice(config.THEMES)
                try:
                    qs = ai.generate_questions(
                        la_count, math_count, weak, prefs=prefs, theme=theme,
                        difficulty=difficulty, subtopic_plan=subtopic_plan,
                    )
                    _note_ai(True, "question generation succeeded")
                except Exception as e:
                    _note_ai(False, f"question generation failed: {e}")
                    return  # network/API problem — try again on the next quest
                qs = [q for q in qs if bank.valid_question(q)]
                if len(qs) < threshold:
                    return  # weak result; don't spin uselessly
                sessions = storage.get_json(_pool_key(pid), [])
                # verified: generate_questions already ran the MC audit.
                sessions.append({"theme": theme, "difficulty": difficulty,
                                 "questions": qs, "verified": True})
                storage.set_json(_pool_key(pid), sessions)
                share_questions(qs)  # audited → into the communal bank
            # Daily quests come first; only once that pool is full do we brew
            # expedition trivia with the leftover background time.
            _fill_expeditions(pid)
        finally:
            with _refill_lock:
                _refilling.discard(pid)

    threading.Thread(target=_worker, daemon=True).start()


# ─── Expeditions: trivia side-quests earning Sparks + stickers ──────────────

def _expool_key(pid):
    return f"expool:{pid}"


def _expool_take(pid, topic=None):
    """Pop a pre-brewed expedition — the requested topic, or any if None.
    Same serve gate as quests: only audited (verified) entries are served."""
    sessions = storage.get_json(_expool_key(pid), [])
    for i, s in enumerate(sessions):
        if s.get("verified") and (topic is None or s.get("topic") == topic):
            sessions.pop(i)
            storage.set_json(_expool_key(pid), sessions)
            return s
    return None


def _fill_expeditions(pid):
    """Blocking; runs inside the refill worker after the quest pool is full.

    Topic choice matters: a kid who just played Civics from the offline bank
    wants FRESH Civics next time, so a requested-but-unpooled topic
    (expedition_wanted) brews first; otherwise prefer topics not already
    queued so the pool stays varied."""
    while len(storage.get_json(_expool_key(pid), [])) < EXPOOL_TARGET:
        pooled_topics = {s.get("topic")
                         for s in storage.get_json(_expool_key(pid), [])}
        p = get_player(pid) or {}
        wanted = p.get("expedition_wanted")
        if wanted in expeditions.TOPICS and wanted not in pooled_topics:
            topic = wanted
        else:
            unpooled = [t for t in expeditions.TOPICS if t not in pooled_topics]
            topic = random.choice(unpooled or list(expeditions.TOPICS))
        label, emoji, desc = expeditions.TOPICS[topic]
        try:
            qs = ai.generate_expedition(topic, label, desc, n=EXPEDITION_SIZE)
            _note_ai(True, "expedition generation succeeded")
        except Exception as e:
            _note_ai(False, f"expedition generation failed: {e}")
            return
        qs = [q for q in qs if expeditions.valid_question(q)]
        if len(qs) < 3:
            return
        sessions = storage.get_json(_expool_key(pid), [])
        # verified: generate_expedition already ran the MC audit.
        sessions.append({"topic": topic, "questions": qs, "verified": True})
        storage.set_json(_expool_key(pid), sessions)
        share_questions(qs)  # audited → into the communal bank
        p = get_player(pid)
        if p and p.get("expedition_wanted") == topic:  # wish granted
            p["expedition_wanted"] = None
            save_player(p)


def start_expedition(p, topic=None):
    """Like start_quest, but trivia: 5 questions, Sparks instead of XP, no
    streak/difficulty involvement. Serves a pre-brewed AI expedition when one
    matches, else the curated offline trivia bank — always instant."""
    # No escaping into an expedition mid-quest (or vice versa): an
    # unfinished session of any kind resumes instead.
    active = active_quest(p)
    if active:
        return _resume_payload(active)
    if topic is not None and topic not in expeditions.TOPICS:
        raise KeyError(topic)
    blocked = blocked_ids()
    qs = []
    pooled = _expool_take(p["id"], topic)
    if pooled:
        topic = pooled["topic"]
        qs = [q for q in pooled["questions"]
              if expeditions.valid_question(q) and q.get("id") not in blocked]
    if len(qs) < 3:
        topic = topic or random.choice(list(expeditions.TOPICS))
        exclude = set(p["offline"]["mastered"]) | blocked
        # Communal AI questions for this topic first, then the curated bank.
        qs = shared_sample(f"shared_bank:x:{topic}", EXPEDITION_SIZE, exclude)
        if len(qs) < EXPEDITION_SIZE:
            have = {q["id"] for q in qs}
            qs += [q for q in expeditions.sample(topic, EXPEDITION_SIZE, exclude)
                   if q["id"] not in have][: EXPEDITION_SIZE - len(qs)]
        # Served from banks — remember the topic so the brewer makes fresh
        # AI questions for it before anything else.
        p["expedition_wanted"] = topic
    seen = set()
    unique = []
    for q in qs:
        q["id"] = q.get("id") or bank.question_id(q)
        if q["id"] not in seen:
            seen.add(q["id"])
            unique.append(bank.ensure_option_letters(q))
    qs = unique[:EXPEDITION_SIZE]
    refill_pool_in_background(p)

    label, emoji, _ = expeditions.TOPICS[topic]
    now = datetime.now(timezone.utc).isoformat()
    quest = {
        "id": str(uuid.uuid4()),
        "kind": "expedition",
        "topic": topic,
        "player_id": p["id"],
        "questions": qs,
        "results": [],
        "xp_gained": 0,  # holds Sparks for expeditions
        "correct_count": 0,
        "streak_continued": False,
        "started_at": now,
        "q_started_at": now,
    }
    p["active_quest"] = quest["id"]
    save_player(p)
    storage.set_json(_quest_key(quest["id"]), quest)
    log_activity(p, "expedition_start", {"topic": label})
    return {
        "quest_id": quest["id"],
        "kind": "expedition",
        "topic": {"key": topic, "name": label, "emoji": emoji},
        "questions": [sanitize_question(q) for q in qs],
        "answered": 0,
        "correct_so_far": 0,
        "resumed": False,
        "ai_graded": bool(config.MINIMAX_API_KEY),
        "question_seconds": config.QUESTION_SECONDS,
    }


# ─── The quest lifecycle: start → answer × n → complete ─────────────────────

def _quest_key(qid):
    return f"quest:{qid}"


def get_quest(qid):
    return storage.get_json(_quest_key(qid))


def active_quest(p):
    """The player's unfinished session, if any. This is the anti-rage-quit
    core: while one exists, the start endpoints return IT instead of a fresh
    session — closing the browser mid-game changes nothing, because every
    answered question already lives here on the server."""
    qid = p.get("active_quest")
    if not qid:
        return None
    return get_quest(qid)


def _resume_payload(quest):
    """Re-enter an in-flight session at the first unanswered question. The
    current question's clock restarts (closing the tab shouldn't auto-fail
    the question a kid was reading), but answered ones are locked in."""
    quest["q_started_at"] = datetime.now(timezone.utc).isoformat()
    storage.set_json(_quest_key(quest["id"]), quest)
    out = {
        "quest_id": quest["id"],
        "kind": quest.get("kind", "quest"),
        "questions": [sanitize_question(q) for q in quest["questions"]],
        "answered": len(quest["results"]),
        "correct_so_far": quest["correct_count"],
        "resumed": True,
        "ai_graded": bool(config.MINIMAX_API_KEY),
        "question_seconds": config.QUESTION_SECONDS,
    }
    if quest.get("kind") == "expedition":
        label, emoji, _ = expeditions.TOPICS[quest["topic"]]
        out["topic"] = {"key": quest["topic"], "name": label, "emoji": emoji}
    if quest.get("kind") == "reading":
        info = books.BOOKS[quest["book"]]
        out["book"] = {"key": quest["book"], "title": info["title"],
                       "emoji": info["emoji"], "chapter": quest["chapter"]}
    return out


def start_quest(p, local_date=None):
    # Unfinished session (of either kind)? You finish it — no fresh starts.
    active = active_quest(p)
    if active:
        return _resume_payload(active)

    today = _client_date(local_date)
    streak_continued = _update_streak(p, today)
    n = config.QUESTIONS_PER_SESSION
    questions = _fetch_questions(p, n)

    now = datetime.now(timezone.utc).isoformat()
    quest = {
        "id": str(uuid.uuid4()),
        "player_id": p["id"],
        "questions": questions,
        "results": [],  # one entry per answered question, in order
        "xp_gained": 0,
        "correct_count": 0,
        "streak_continued": streak_continued,
        "started_at": now,
        "q_started_at": now,
    }
    p["active_quest"] = quest["id"]
    save_player(p)
    refill_pool_in_background(p)
    storage.set_json(_quest_key(quest["id"]), quest)
    log_activity(p, "quest_start", {"questions": len(questions)})
    return {
        "quest_id": quest["id"],
        "kind": "quest",
        "questions": [sanitize_question(q) for q in questions],
        "answered": 0,
        "correct_so_far": 0,
        "resumed": False,
        "ai_graded": bool(config.MINIMAX_API_KEY),
        "question_seconds": config.QUESTION_SECONDS,
    }


def _grade(q, answer):
    """Returns (correct, feedback). MC is checked locally; short answers go to
    MiniMax when available, else the CLI's keyword-overlap fallback."""
    if q["type"] == "mc":
        correct = answer.strip().upper()[:1] == str(q["answer"]).strip().upper()[:1]
        return correct, q.get("explanation", "")
    if config.MINIMAX_API_KEY:
        try:
            result = ai.grade_short_answer(q, answer)
            _note_ai(True, "short-answer grading succeeded")
            return result
        except Exception as e:
            _note_ai(False, f"short-answer grading failed: {e}")
    expected = set(str(q["answer"]).lower().split())
    given = set(answer.lower().split())
    correct = len(expected & given) >= max(1, math.ceil(len(expected) * 0.2))
    return correct, q.get("explanation", "")


TIMEOUT_FEEDBACK = "⏰ Time's up! No worries — read fast, think smart, and grab the next one."
# Server-side backstop past the client's countdown. Generous because legit
# things eat clock the client knows about and we don't (boss-intro reading,
# a slow network, a tab briefly backgrounded) — the client timer is the
# pacing enforcer; this only catches a client that's lying or broken.
TIMEOUT_GRACE_SECONDS = 60


def answer_question(quest, answer, timed_out=False, player=None):
    """Grade the next unanswered question, update the profile, return the
    reveal. Questions are strictly in order — the index is len(results).
    Expeditions pay Sparks instead of XP and have no boss. Pass `player`
    when already loaded (the API auth path has it) to skip a store read."""
    i = len(quest["results"])
    if i >= len(quest["questions"]):
        raise IndexError("quest already complete")
    q = quest["questions"][i]
    is_expedition = quest.get("kind") == "expedition"
    # Only daily quests have a boss; expeditions and reading quizzes don't.
    is_boss = (quest.get("kind", "quest") == "quest"
               and i == len(quest["questions"]) - 1)

    if not timed_out and quest.get("q_started_at"):
        elapsed = (
            datetime.now(timezone.utc)
            - datetime.fromisoformat(quest["q_started_at"])
        ).total_seconds()
        timed_out = elapsed > config.QUESTION_SECONDS + TIMEOUT_GRACE_SECONDS

    if timed_out:
        correct, feedback = False, TIMEOUT_FEEDBACK
        answer = answer or "(time ran out)"
    else:
        correct, feedback = _grade(q, answer)
    if is_expedition:
        xp = SPARKS_PER_CORRECT
    else:
        xp = config.XP_PER_CORRECT * (config.XP_BOSS_MULTIPLIER if is_boss else 1)

    p = player or get_player(quest["player_id"])
    if correct:
        quest["correct_count"] += 1
        quest["xp_gained"] += xp
        if is_expedition:
            p["sparks"] = p.get("sparks", 0) + xp
        else:
            p["xp"] += xp
            if is_boss:
                p["boss_wins"] += 1
    if not is_expedition:  # expedition topics aren't MCA categories
        profile_mod.record_answer(p, q["category"], correct, q.get("subtopic"))
    if q.get("id"):
        profile_mod.record_offline(p, q["id"], correct)
    save_player(p)

    # `answer` and `feedback` are kept so a challenge can re-try the ruling.
    quest["results"].append({
        "category": q["category"],
        "correct": correct,
        "answer": answer,
        "feedback": feedback,
    })
    quest["q_started_at"] = datetime.now(timezone.utc).isoformat()  # next q's clock
    storage.set_json(_quest_key(quest["id"]), quest)

    return {
        "correct": correct,
        "feedback": feedback,
        "xp_gained": xp if correct else 0,
        "is_boss": is_boss,
        "answer": str(q["answer"]),
        "explanation": q.get("explanation", ""),
        "index": i,
        "remaining": len(quest["questions"]) - len(quest["results"]),
    }


def _standings_for(p):
    """Post-quest leaderboard context: this player's rank plus the XP gaps to
    the players just ahead and just behind — the raw material for the results
    screen's compare-and-contrast moment."""
    rows = leaderboard()
    me = next((i for i, r in enumerate(rows) if r["id"] == p["id"]), None)
    if me is None:
        return None
    slim = lambda r: {"name": r["name"], "xp": r["xp"],
                      "level_num": r["level_num"], "level_title": r["level_title"]}
    return {
        "rank": me + 1,
        "of": len(rows),
        "me": slim(rows[me]),
        "ahead": slim(rows[me - 1]) if me > 0 else None,
        "behind": slim(rows[me + 1]) if me + 1 < len(rows) else None,
        "leader": slim(rows[0]) if me > 0 else None,
    }


def merge_offer_payload(p):
    """A pending combine-profiles offer (set on the player record by a
    parent), enriched with what accepting would mean — or None. Everything
    shown is literally true: the old profile, its XP, the bonus, and the
    level the combined profile would reach."""
    offer = p.get("merge_offer") or {}
    src = get_player(offer.get("source_pid", ""))
    if not src:
        return None
    bonus = int(offer.get("bonus_xp", 0))
    src_num, src_title, _ = profile_mod.level_info(src["xp"])
    merged_xp = p["xp"] + src["xp"] + bonus
    merged_num, merged_title, _ = profile_mod.level_info(merged_xp)
    return {
        "message": offer.get("message")
        or "We noticed another profile that looks like yours. Combine them?",
        "source_name": src["name"],
        "source_xp": src["xp"],
        "source_level": src_num,
        "source_level_title": src_title,
        "bonus_xp": bonus,
        "merged_xp": merged_xp,
        "merged_level": merged_num,
        "merged_level_title": merged_title,
    }


def accept_merge(p):
    """Fold the offered old profile into this one — XP (plus the reunion
    bonus), per-category and per-subtopic stats, badges, mastery, stickers,
    history — then retire the old profile and its queues."""
    offer = p.get("merge_offer") or {}
    src = get_player(offer.get("source_pid", ""))
    if not src:
        raise ValueError("no profile to combine")
    src = _normalize(src)
    p = _normalize(p)
    bonus = int(offer.get("bonus_xp", 0))

    p["xp"] += src["xp"] + bonus
    for k, v in src["totals"].items():
        p["totals"][k] = p["totals"].get(k, 0) + v
    for cat, stats in src["categories"].items():
        mine = p["categories"].setdefault(cat, {"answered": 0, "correct": 0})
        mine["answered"] += stats.get("answered", 0)
        mine["correct"] += stats.get("correct", 0)
    for cat, subs in src["subtopics"].items():
        mine = p.setdefault("subtopics", {}).setdefault(cat, {})
        for sub, stats in subs.items():
            m = mine.setdefault(sub, {"answered": 0, "correct": 0})
            m["answered"] += stats.get("answered", 0)
            m["correct"] += stats.get("correct", 0)
    for b in src["badges"]:
        if b not in p["badges"]:
            p["badges"].append(b)
    mine, theirs = p["offline"], src["offline"]
    mine["mastered"] += [q for q in theirs["mastered"]
                         if q not in mine["mastered"]]
    mine["review"] += [q for q in theirs["review"]
                       if q not in mine["review"] and q not in mine["mastered"]]
    p["boss_wins"] = p.get("boss_wins", 0) + src.get("boss_wins", 0)
    p["sessions_completed"] += src["sessions_completed"]
    p["streak"] = max(p.get("streak", 0), src.get("streak", 0))
    p["sparks"] = p.get("sparks", 0) + src.get("sparks", 0)
    for topic, n in src["stickers"].items():
        p["stickers"][topic] = p["stickers"].get(topic, 0) + n
    for k, v in src["prefs"].items():
        p["prefs"].setdefault(k, v)
    p.pop("merge_offer", None)
    save_player(p)

    # The old profile's story joins this player's history, oldest first.
    old_history = get_history(src["id"])
    if old_history:
        merged = sorted(old_history + get_history(p["id"]),
                        key=lambda h: h.get("timestamp") or "")
        storage.set_json(_history_key(p["id"]), merged)
    for key in (_player_key(src["id"]), _history_key(src["id"]),
                _pool_key(src["id"]), _expool_key(src["id"])):
        storage.store.delete(key)

    return {"restored_xp": src["xp"], "bonus_xp": bonus,
            "player": public_player(p)}


def complete_quest(quest, player=None):
    """Streak bonus, badges, history — then the quest record is deleted."""
    if len(quest["results"]) < len(quest["questions"]):
        raise ValueError("quest still has unanswered questions")
    if quest.get("kind") == "expedition":
        return _complete_expedition(quest, player)
    if quest.get("kind") == "reading":
        return _complete_reading(quest, player)
    p = player or get_player(quest["player_id"])

    xp_gained = quest["xp_gained"]
    streak_bonus = (
        config.XP_STREAK_BONUS * p["streak"] if quest["streak_continued"] else 0
    )
    p["xp"] += streak_bonus
    xp_gained += streak_bonus

    total = len(quest["questions"])
    p["sessions_completed"] = p.get("sessions_completed", 0) + 1
    new_badges = profile_mod.check_badges(p, quest["correct_count"] == total)
    difficulty_delta = profile_mod.adjust_difficulty(p, quest["correct_count"], total)
    p["active_quest"] = None
    save_player(p)

    summary = {
        "player_id": p["id"],
        "player_name": p["name"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "score": quest["correct_count"],
        "total": total,
        "xp_gained": xp_gained,
        "streak": p["streak"],
        "ai_powered": bool(config.MINIMAX_API_KEY),
        "results": quest["results"],
    }
    append_history(p["id"], summary)
    storage.store.delete(_quest_key(quest["id"]))
    refill_pool_in_background(p)
    log_activity(p, "quest_done", {
        "score": quest["correct_count"], "total": total, "xp": xp_gained,
    })

    return {
        "score": quest["correct_count"],
        "total": total,
        "xp_gained": xp_gained,
        "streak_bonus": streak_bonus,
        "new_badges": [
            {"key": b, "label": profile_mod.BADGES[b][0], "desc": profile_mod.BADGES[b][1]}
            for b in new_badges
        ],
        "difficulty": p["difficulty"],
        "difficulty_delta": difficulty_delta,
        "player": public_player(p),
        # Post-quest compare-and-contrast against the family board, and (if a
        # parent queued one) the combine-profiles offer — shown after it.
        "standings": _standings_for(p),
        "merge_offer": merge_offer_payload(p),
    }


def _complete_expedition(quest, player=None):
    """Award the topic sticker, log it, clean up. No streak/badge/difficulty
    involvement — expeditions are their own light economy."""
    p = player or get_player(quest["player_id"])
    topic = quest["topic"]
    stickers = p.setdefault("stickers", {})
    stickers[topic] = stickers.get(topic, 0) + 1
    p["active_quest"] = None
    save_player(p)

    label, emoji, _ = expeditions.TOPICS[topic]
    append_history(p["id"], {
        "kind": "expedition",
        "topic": topic,
        "player_id": p["id"],
        "player_name": p["name"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "score": quest["correct_count"],
        "total": len(quest["questions"]),
        "sparks_gained": quest["xp_gained"],
    })
    storage.store.delete(_quest_key(quest["id"]))
    refill_pool_in_background(p)
    log_activity(p, "expedition_done", {
        "topic": label, "score": quest["correct_count"],
        "total": len(quest["questions"]), "sparks": quest["xp_gained"],
    })

    return {
        "kind": "expedition",
        "score": quest["correct_count"],
        "total": len(quest["questions"]),
        "sparks_earned": quest["xp_gained"],
        "sticker": {"key": topic, "name": label, "emoji": emoji,
                    "count": stickers[topic]},
        "player": public_player(p),
    }


# ─── Reading Room: progress, chapter quizzes ────────────────────────────────

READING_QUIZ_SIZE = 3


def _quiz_key(book, chapter):
    return f"bookquiz:{book}:{chapter}"


_brewing_quizzes = set()
_brew_lock = threading.Lock()


def brew_reading_quiz_in_background(book, chapter):
    """Generate the chapter's quiz while the kid is reading — one quiz per
    chapter, cached and shared by the whole family. No-op if cached,
    already brewing, or no API key."""
    if not config.MINIMAX_API_KEY:
        return
    key = _quiz_key(book, chapter)
    with _brew_lock:
        if key in _brewing_quizzes or storage.get_json(key):
            return
        _brewing_quizzes.add(key)

    def _worker():
        try:
            ch, _total = books.get_chapter(book, chapter)
            info = books.BOOKS[book]
            try:
                qs = ai.generate_reading_quiz(
                    info["title"], info["author"], ch["text"], n=READING_QUIZ_SIZE
                )
                _note_ai(True, "reading quiz generation succeeded")
            except Exception as e:
                _note_ai(False, f"reading quiz generation failed: {e}")
                return
            qs = [q for q in qs if bank.valid_question(q)]
            if len(qs) >= 2:
                storage.set_json(key, qs[:READING_QUIZ_SIZE])
        finally:
            with _brew_lock:
                _brewing_quizzes.discard(key)

    threading.Thread(target=_worker, daemon=True).start()


def reading_progress(p, book):
    return p.get("reading", {}).get(book, {"finished": 0, "quizzed": []})


def open_chapter(p, book, chapter):
    """Serve a chapter and kick off its quiz brew. The reader's front door."""
    ch, total = books.get_chapter(book, chapter)
    brew_reading_quiz_in_background(book, chapter)
    prog = reading_progress(p, book)
    log_activity(p, "reading", {"book": books.BOOKS[book]["title"],
                                "chapter": chapter + 1,
                                "chapter_title": ch["title"]})
    return {
        "book": book,
        "index": chapter,
        "chapters": total,
        "chapter_title": ch["title"],
        "text": ch["text"],
        "finished_through": prog["finished"],
        "quizzed": chapter in prog["quizzed"],
        "quiz_ready": bool(storage.get_json(_quiz_key(book, chapter))),
    }


def finish_chapter(p, book, chapter):
    """Mark reading progress (no XP here — the quiz is where XP lives, so
    clicking 'next' through a book earns nothing)."""
    reading = p.setdefault("reading", {})
    prog = reading.setdefault(book, {"finished": 0, "quizzed": []})
    prog["finished"] = max(prog["finished"], chapter + 1)
    save_player(p)
    return {"finished_through": prog["finished"],
            "quiz_ready": bool(storage.get_json(_quiz_key(book, chapter)))}


class QuizNotReady(Exception):
    pass


def start_reading_quiz(p, book, chapter):
    """A 3-question comprehension quiz on the exact chapter just read.
    Same session machinery as quests: resume-forced, timed, challengeable."""
    active = active_quest(p)
    if active:
        return _resume_payload(active)
    if book not in books.BOOKS:
        raise KeyError(book)
    qs = storage.get_json(_quiz_key(book, chapter))
    if not qs:
        brew_reading_quiz_in_background(book, chapter)
        raise QuizNotReady()
    blocked = blocked_ids()
    prepared = []
    for q in qs:
        q = dict(q)
        q["id"] = q.get("id") or bank.question_id(q)
        if q["id"] not in blocked:
            prepared.append(bank.ensure_option_letters(q))
    if len(prepared) < 2:
        storage.store.delete(_quiz_key(book, chapter))  # rotten quiz — re-brew
        brew_reading_quiz_in_background(book, chapter)
        raise QuizNotReady()

    info = books.BOOKS[book]
    now = datetime.now(timezone.utc).isoformat()
    quest = {
        "id": str(uuid.uuid4()),
        "kind": "reading",
        "book": book,
        "chapter": chapter,
        "player_id": p["id"],
        "questions": prepared,
        "results": [],
        "xp_gained": 0,
        "correct_count": 0,
        "streak_continued": False,
        "started_at": now,
        "q_started_at": now,
    }
    p["active_quest"] = quest["id"]
    save_player(p)
    storage.set_json(_quest_key(quest["id"]), quest)
    log_activity(p, "reading_quiz_start",
                 {"book": info["title"], "chapter": chapter + 1})
    return {
        "quest_id": quest["id"],
        "kind": "reading",
        "book": {"key": book, "title": info["title"], "emoji": info["emoji"],
                 "chapter": chapter},
        "questions": [sanitize_question(q) for q in prepared],
        "answered": 0,
        "correct_so_far": 0,
        "resumed": False,
        "ai_graded": bool(config.MINIMAX_API_KEY),
        "question_seconds": config.QUESTION_SECONDS,
    }


def _complete_reading(quest, player=None):
    p = player or get_player(quest["player_id"])
    book, chapter = quest["book"], quest["chapter"]
    reading = p.setdefault("reading", {})
    prog = reading.setdefault(book, {"finished": 0, "quizzed": []})
    if chapter not in prog["quizzed"]:
        prog["quizzed"].append(chapter)
    prog["finished"] = max(prog["finished"], chapter + 1)
    p["active_quest"] = None
    save_player(p)

    info = books.BOOKS[book]
    append_history(p["id"], {
        "kind": "reading",
        "book": book,
        "chapter": chapter,
        "player_id": p["id"],
        "player_name": p["name"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "score": quest["correct_count"],
        "total": len(quest["questions"]),
        "xp_gained": quest["xp_gained"],
    })
    storage.store.delete(_quest_key(quest["id"]))
    log_activity(p, "reading_quiz_done", {
        "book": info["title"], "chapter": chapter + 1,
        "score": quest["correct_count"], "total": len(quest["questions"]),
        "xp": quest["xp_gained"],
    })
    return {
        "kind": "reading",
        "score": quest["correct_count"],
        "total": len(quest["questions"]),
        "xp_gained": quest["xp_gained"],
        "book": {"key": book, "title": info["title"], "emoji": info["emoji"],
                 "chapter": chapter},
        "player": public_player(p),
    }


# ─── Challenges (appeals) + issue reports ───────────────────────────────────

REPORTS_KEY = "reports"
MAX_REPORTS = 200


def file_report(player, quest, index, rtype, note=""):
    """Store an issue for the parent to review at GET /api/v1/reports —
    full context: the question (with official answer), what the kid wrote,
    and the feedback they were shown."""
    q = quest["questions"][index]
    entry = quest["results"][index] if index < len(quest["results"]) else {}
    reports = storage.get_json(REPORTS_KEY, [])
    reports.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": rtype,  # challenge_won | manual
        "player_name": player.get("name"),
        "kind": quest.get("kind", "quest"),
        "question": q,
        "student_answer": entry.get("answer"),
        "feedback_shown": entry.get("feedback"),
        "note": str(note)[:300],
    })
    storage.set_json(REPORTS_KEY, reports[-MAX_REPORTS:])


def file_simple_report(player, rtype, note=""):
    """Quest-free report — e.g. a locked-out kid asking for a password reset."""
    reports = storage.get_json(REPORTS_KEY, [])
    reports.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": rtype,
        "player_name": player.get("name"),
        "player_id": player.get("id"),
        "note": str(note)[:300],
    })
    storage.set_json(REPORTS_KEY, reports[-MAX_REPORTS:])


def get_reports():
    return storage.get_json(REPORTS_KEY, [])


def clear_reports():
    storage.store.delete(REPORTS_KEY)


def challenge_answer(quest, index, player=None):
    """Adversarial re-evaluation of a ruling the learner disputes. One
    challenge per question. An overturn pays the XP/Sparks retroactively,
    corrects every stat the original ruling touched, and auto-files a
    report so the parent sees each AI mistake."""
    if index >= len(quest["results"]):
        raise IndexError("that question hasn't been answered")
    entry = quest["results"][index]
    if entry.get("correct"):
        raise ValueError("that answer was already ruled correct")
    if entry.get("challenged"):
        raise ValueError("that ruling has already been challenged")
    if not config.MINIMAX_API_KEY:
        return {"overturned": False, "unavailable": True,
                "message": "The appeals judge is offline right now — ask a grown-up to check this one."}

    q = quest["questions"][index]
    # Multiple choice is graded by letter match in code, so no grader can have
    # erred — the only live question is whether the KEY is wrong, and that gets
    # the strict answer-key audit. Written answers keep the sympathetic appeals
    # judge, which exists precisely because AI grading of prose can be wrong.
    is_mc = bool(q.get("options"))
    try:
        if is_mc:
            overturned, message = ai.audit_mc_challenge(q, entry.get("answer", ""))
        else:
            overturned, message = ai.challenge_grading(
                q, entry.get("answer", ""), entry.get("feedback", "")
            )
        _note_ai(True, "challenge review succeeded")
    except Exception as e:
        _note_ai(False, f"challenge review failed: {e}")
        return {"overturned": False, "unavailable": True,
                "message": "The appeals judge couldn't be reached — try again in a minute."}

    entry["challenged"] = True
    xp_awarded = 0
    p = player or get_player(quest["player_id"])
    if overturned:
        entry["correct"] = True
        is_expedition = quest.get("kind") == "expedition"
        is_boss = (quest.get("kind", "quest") == "quest"
                   and index == len(quest["questions"]) - 1)
        if is_expedition:
            xp_awarded = SPARKS_PER_CORRECT
            p["sparks"] = p.get("sparks", 0) + xp_awarded
        else:
            xp_awarded = config.XP_PER_CORRECT * (
                config.XP_BOSS_MULTIPLIER if is_boss else 1
            )
            p["xp"] += xp_awarded
            if is_boss:
                p["boss_wins"] += 1
            # The original ruling logged answered+wrong; flip it to correct.
            cat = p["categories"].get(q["category"])
            if cat:
                cat["correct"] += 1
            p["totals"]["correct"] += 1
            key = ("math_correct"
                   if config.CATEGORIES.get(q["category"]) == "math"
                   else "la_correct")
            p["totals"][key] += 1
        quest["correct_count"] += 1
        quest["xp_gained"] += xp_awarded
        if q.get("id"):
            profile_mod.record_offline(p, q["id"], True)
            # An overturned ruling means the question (or its key) is bad —
            # pull it from everyone's rotation pending parent review.
            block_question(q["id"], "challenge_overturned", q.get("question", ""))
        save_player(p)
        file_report(p, quest, index, "challenge_won",
                    note="auto-filed: the answer-key audit found this key wrong"
                    if is_mc else
                    "auto-filed: the appeals judge overturned this ruling")
    storage.set_json(_quest_key(quest["id"]), quest)
    log_activity(p, "challenge", {
        "overturned": bool(overturned),
        "question": (q.get("question") or "")[:120],
    })
    return {"overturned": overturned, "message": message, "xp_awarded": xp_awarded}


# ─── Activity log (parent view) ──────────────────────────────────────────────
# A per-player breadcrumb trail: signing in and out, and what happened in
# between. Written on session boundaries only — never per answer — so it
# costs one small store write at moments that are already slow (a quest
# start), not on the latency-critical answer path.

ACTIVITY_MAX = 400  # events kept per player (oldest fall off)
SEEN_REFRESH_SECONDS = 300


def _activity_key(pid):
    return f"activity:{pid}"


def log_activity(p, kind, detail=None):
    """Record one event. `p` may be a player dict or a bare player id."""
    pid = p["id"] if isinstance(p, dict) else p
    if not pid:
        return
    events = storage.get_json(_activity_key(pid), [])
    events.append({
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "kind": kind,
        "detail": detail or {},
    })
    storage.set_json(_activity_key(pid), events[-ACTIVITY_MAX:])


def get_activity(pid):
    return storage.get_json(_activity_key(pid), [])


def touch_seen(p):
    """Cheap 'still here' marker for the parent view. Throttled hard: the
    home screen refetches the player on every navigation, and a write per
    hop would add a store round trip to a hot path for no new information."""
    now = datetime.now(timezone.utc)
    last = p.get("last_seen")
    if last:
        try:
            if (now - datetime.fromisoformat(last)).total_seconds() < SEEN_REFRESH_SECONDS:
                return
        except ValueError:
            pass
    p["last_seen"] = now.isoformat(timespec="seconds")
    save_player(p)


def _minutes_between(a, b):
    try:
        return max(0, round(
            (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() / 60
        ))
    except (ValueError, TypeError):
        return 0


def activity_sessions(days=14):
    """The parent view's shape: one entry per sign-in, holding everything
    that happened before the sign-out (or before the trail went cold).

    Events are grouped rather than listed flat because 'when did they log in
    and out' is a question about spans, not instants. A session with no
    logout stays open — kids close the tab far more often than they press
    'switch player' — so `signed_out` distinguishes a real sign-out from a
    walk-away, and `end` is then the last thing they actually did."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, days))).isoformat()
    out, failed = [], []
    for p in list_players():
        current = None
        for e in get_activity(p["id"]):
            if e.get("ts", "") < cutoff:
                continue
            if e["kind"] == "login_failed":
                # A wrong password isn't a session — it's an attempt to start
                # one. Kept apart so it can't masquerade as time spent.
                failed.append({"player_id": p["id"], "player_name": p.get("name", ""),
                               "ts": e["ts"]})
                continue
            if e["kind"] == "login" or current is None:
                if current:
                    out.append(current)
                current = {
                    "player_id": p["id"],
                    "player_name": p.get("name", ""),
                    "start": e["ts"],
                    "end": e["ts"],
                    "signed_out": False,
                    "events": [],
                }
            current["end"] = e["ts"]
            if e["kind"] == "logout":
                current["signed_out"] = True
                out.append(current)
                current = None
            elif e["kind"] != "login":
                current["events"].append(e)
        if current:
            out.append(current)
    for s in out:
        s["minutes"] = _minutes_between(s["start"], s["end"])
    out.sort(key=lambda s: s["start"], reverse=True)
    failed.sort(key=lambda f: f["ts"], reverse=True)
    return out, failed


def activity_overview(days=14):
    """Sessions plus a per-player roll-up, so the parent view can lead with
    'who has been on lately' before the detail."""
    sessions, failed = activity_sessions(days)
    players = []
    for p in list_players():
        mine = [s for s in sessions if s["player_id"] == p["id"]]
        players.append({
            "id": p["id"],
            "name": p.get("name", ""),
            "last_seen": p.get("last_seen"),
            "sessions": len(mine),
            "minutes": sum(s["minutes"] for s in mine),
            "activities": sum(len(s["events"]) for s in mine),
            "failed_logins": sum(1 for f in failed if f["player_id"] == p["id"]),
        })
    players.sort(key=lambda r: (r["last_seen"] or "", r["name"]), reverse=True)
    return {"days": days, "players": players, "sessions": sessions,
            "failed_logins": failed}


# ─── History + CLI sync ──────────────────────────────────────────────────────

def _history_key(pid):
    return f"history:{pid}"


def append_history(pid, summary):
    history = storage.get_json(_history_key(pid), [])
    history.append(summary)
    storage.set_json(_history_key(pid), history)


def get_history(pid):
    return storage.get_json(_history_key(pid), [])


def ingest_cli_progress(profile, session_summary):
    """The sync.py contract: the CLI pushes its full profile + a session
    summary. The profile is authoritative for the GAME state of that player
    id, but server-only fields (auth secret, tokens, sparks/stickers, active
    web session) must survive the overwrite — the CLI knows nothing of them."""
    pid = profile.get("id")
    if not pid:
        raise ValueError("profile.id required")
    existing = get_player(pid)
    if existing:
        for k in ("secret_hash", "secret_hint", "auth_gen", "active_quest",
                  "sparks", "stickers", "expedition_wanted", "last_seen"):
            if k in existing and k not in profile:
                profile[k] = existing[k]
        # A rename done in the web app wins over the name the CLI still has.
        if existing.get("renamed_at"):
            profile["name"] = existing["name"]
            profile["renamed_at"] = existing["renamed_at"]
    save_player(_normalize(profile))
    if session_summary:
        append_history(pid, session_summary)
