"""Server-side game engine — the CLI's daily-quest loop, re-cut for HTTP.

Reuses the quest package verbatim: ai.py for MiniMax generation/grading,
bank.py for the offline pack + validation + no-repeat ids, profile.py for
badges/levels, config.py for constants. What changes is where state lives
(the kv store instead of local JSON files) and that the question pool is
per player instead of per machine.

Answers never leave the server: the client gets sanitized questions and
posts answers back one at a time for grading, so the browser can't peek.
"""
import math
import random
import re
import threading
import uuid
from datetime import date, datetime, timedelta, timezone

from quest import ai, bank, config, expeditions, profile as profile_mod

from . import storage

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
    p.setdefault("prefs", {}).update(clean_prefs(new_prefs))
    save_player(p)
    return p


def public_player(p):
    """Profile + everything the frontend needs pre-computed (level, badges)."""
    p = _normalize(dict(p))
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


# ─── Question selection (mirrors session.py) ────────────────────────────────

def _build_mix(n):
    la_count = round(n * config.LA_RATIO)
    return la_count, n - la_count


def _finalize(p, questions, n, la_count):
    """No repeats from ANY source: drop mastered/duplicate questions by
    content-hash id, top back up from the bank, guarantee option letters."""
    off = p["offline"]
    mastered = set(off["mastered"])
    used, result = set(), []
    for q in questions:
        qid = q.get("id") or bank.question_id(q)
        q["id"] = qid
        if qid in mastered or qid in used:
            continue
        used.add(qid)
        result.append(q)
    if len(result) < n:
        for q in bank.sample(n - len(result), la_count, mastered | used, off["review"]):
            if q["id"] not in used:
                used.add(q["id"])
                result.append(q)
    return [bank.ensure_option_letters(q) for q in result[:n]]


def _offline_raw(p, prefs, n, la_count):
    extras = [q for q in bank.personalized(prefs) if bank.valid_question(q)][: min(2, n)]
    off = p["offline"]
    filler = bank.sample(n - len(extras), la_count, off["mastered"], off["review"])
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
    sessions = storage.get_json(_pool_key(pid), [])
    if not sessions:
        return None
    first = sessions.pop(0)
    storage.set_json(_pool_key(pid), sessions)
    return first.get("questions", [])


def _pool_count(pid):
    return len(storage.get_json(_pool_key(pid), []))


_refilling = set()
_refill_lock = threading.Lock()


def refill_pool_in_background(p):
    """Brew the next themed, personalized sessions while the kid plays.
    No-op without an API key, if a refill for this player is already running,
    or if their pool is full — same degrade-gracefully rules as the CLI."""
    pid = p["id"]
    if not config.MINIMAX_API_KEY:
        return
    with _refill_lock:
        if pid in _refilling or _pool_count(pid) >= POOL_TARGET:
            return
        _refilling.add(pid)

    la_count, math_count = _build_mix(config.QUESTIONS_PER_SESSION)
    weak = profile_mod.weak_categories(p)
    prefs = p.get("prefs") or {}
    difficulty = p.get("difficulty", 2)

    def _worker():
        try:
            threshold = max(3, (la_count + math_count) // 2)
            while _pool_count(pid) < POOL_TARGET:
                theme = random.choice(config.THEMES)
                try:
                    qs = ai.generate_questions(
                        la_count, math_count, weak, prefs=prefs, theme=theme,
                        difficulty=difficulty,
                    )
                    _note_ai(True, "question generation succeeded")
                except Exception as e:
                    _note_ai(False, f"question generation failed: {e}")
                    return  # network/API problem — try again on the next quest
                qs = [q for q in qs if bank.valid_question(q)]
                if len(qs) < threshold:
                    return  # weak result; don't spin uselessly
                sessions = storage.get_json(_pool_key(pid), [])
                sessions.append({"theme": theme, "difficulty": difficulty,
                                 "questions": qs})
                storage.set_json(_pool_key(pid), sessions)
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
    """Pop a pre-brewed expedition — the requested topic, or any if None."""
    sessions = storage.get_json(_expool_key(pid), [])
    for i, s in enumerate(sessions):
        if topic is None or s.get("topic") == topic:
            sessions.pop(i)
            storage.set_json(_expool_key(pid), sessions)
            return s
    return None


def _fill_expeditions(pid):
    """Blocking; runs inside the refill worker after the quest pool is full."""
    while len(storage.get_json(_expool_key(pid), [])) < EXPOOL_TARGET:
        topic = random.choice(list(expeditions.TOPICS))
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
        sessions.append({"topic": topic, "questions": qs})
        storage.set_json(_expool_key(pid), sessions)


def start_expedition(p, topic=None):
    """Like start_quest, but trivia: 5 questions, Sparks instead of XP, no
    streak/difficulty involvement. Serves a pre-brewed AI expedition when one
    matches, else the curated offline trivia bank — always instant."""
    if topic is not None and topic not in expeditions.TOPICS:
        raise KeyError(topic)
    qs = []
    pooled = _expool_take(p["id"], topic)
    if pooled:
        topic = pooled["topic"]
        qs = [q for q in pooled["questions"] if expeditions.valid_question(q)]
    if len(qs) < 3:
        topic = topic or random.choice(list(expeditions.TOPICS))
        qs = expeditions.sample(topic, EXPEDITION_SIZE, p["offline"]["mastered"])
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
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    storage.set_json(_quest_key(quest["id"]), quest)
    return {
        "quest_id": quest["id"],
        "kind": "expedition",
        "topic": {"key": topic, "name": label, "emoji": emoji},
        "questions": [sanitize_question(q) for q in qs],
        "ai_graded": bool(config.MINIMAX_API_KEY),
    }


# ─── The quest lifecycle: start → answer × n → complete ─────────────────────

def _quest_key(qid):
    return f"quest:{qid}"


def get_quest(qid):
    return storage.get_json(_quest_key(qid))


def start_quest(p, local_date=None):
    today = _client_date(local_date)
    streak_continued = _update_streak(p, today)
    n = config.QUESTIONS_PER_SESSION
    questions = _fetch_questions(p, n)
    save_player(p)
    refill_pool_in_background(p)

    quest = {
        "id": str(uuid.uuid4()),
        "player_id": p["id"],
        "questions": questions,
        "results": [],  # one entry per answered question, in order
        "xp_gained": 0,
        "correct_count": 0,
        "streak_continued": streak_continued,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }
    storage.set_json(_quest_key(quest["id"]), quest)
    return {
        "quest_id": quest["id"],
        "kind": "quest",
        "questions": [sanitize_question(q) for q in questions],
        "ai_graded": bool(config.MINIMAX_API_KEY),
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


def answer_question(quest, answer):
    """Grade the next unanswered question, update the profile, return the
    reveal. Questions are strictly in order — the index is len(results).
    Expeditions pay Sparks instead of XP and have no boss."""
    i = len(quest["results"])
    if i >= len(quest["questions"]):
        raise IndexError("quest already complete")
    q = quest["questions"][i]
    is_expedition = quest.get("kind") == "expedition"
    is_boss = not is_expedition and i == len(quest["questions"]) - 1

    correct, feedback = _grade(q, answer)
    if is_expedition:
        xp = SPARKS_PER_CORRECT
    else:
        xp = config.XP_PER_CORRECT * (config.XP_BOSS_MULTIPLIER if is_boss else 1)

    p = get_player(quest["player_id"])
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
        profile_mod.record_answer(p, q["category"], correct)
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


def complete_quest(quest):
    """Streak bonus, badges, history — then the quest record is deleted."""
    if len(quest["results"]) < len(quest["questions"]):
        raise ValueError("quest still has unanswered questions")
    if quest.get("kind") == "expedition":
        return _complete_expedition(quest)
    p = get_player(quest["player_id"])

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
    }


def _complete_expedition(quest):
    """Award the topic sticker, log it, clean up. No streak/badge/difficulty
    involvement — expeditions are their own light economy."""
    p = get_player(quest["player_id"])
    topic = quest["topic"]
    stickers = p.setdefault("stickers", {})
    stickers[topic] = stickers.get(topic, 0) + 1
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

    return {
        "kind": "expedition",
        "score": quest["correct_count"],
        "total": len(quest["questions"]),
        "sparks_earned": quest["xp_gained"],
        "sticker": {"key": topic, "name": label, "emoji": emoji,
                    "count": stickers[topic]},
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


def get_reports():
    return storage.get_json(REPORTS_KEY, [])


def clear_reports():
    storage.store.delete(REPORTS_KEY)


def challenge_answer(quest, index):
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
    try:
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
    p = get_player(quest["player_id"])
    if overturned:
        entry["correct"] = True
        is_expedition = quest.get("kind") == "expedition"
        is_boss = not is_expedition and index == len(quest["questions"]) - 1
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
        save_player(p)
        file_report(p, quest, index, "challenge_won",
                    note="auto-filed: the appeals judge overturned this ruling")
    storage.set_json(_quest_key(quest["id"]), quest)
    return {"overturned": overturned, "message": message, "xp_awarded": xp_awarded}


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
    summary. The profile is authoritative for that player id (the CLI is the
    source of truth on that machine); the summary is appended to history."""
    pid = profile.get("id")
    if not pid:
        raise ValueError("profile.id required")
    save_player(_normalize(profile))
    if session_summary:
        append_history(pid, session_summary)
