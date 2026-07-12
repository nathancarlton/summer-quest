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

from quest import ai, bank, config, profile as profile_mod

from . import storage

POOL_TARGET = 2  # ready-made themed sessions to keep queued per player

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
    return p


def list_players():
    out = []
    for key in storage.store.keys("player:"):
        p = storage.get_json(key)
        if p:
            out.append(p)
    out.sort(key=lambda p: p.get("name", "").lower())
    return out


def _normalize(p):
    """Same forward-compat defaults profile.load() applies to old files."""
    for c in config.CATEGORIES:
        p["categories"].setdefault(c, {"answered": 0, "correct": 0})
    p.setdefault("sessions_completed", 0)
    p.setdefault("offline", {"mastered": [], "review": []})
    p.setdefault("prefs", {})
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

    def _worker():
        try:
            threshold = max(3, (la_count + math_count) // 2)
            while _pool_count(pid) < POOL_TARGET:
                theme = random.choice(config.THEMES)
                try:
                    qs = ai.generate_questions(
                        la_count, math_count, weak, prefs=prefs, theme=theme
                    )
                except Exception:
                    return  # network/API problem — try again on the next quest
                qs = [q for q in qs if bank.valid_question(q)]
                if len(qs) < threshold:
                    return  # weak result; don't spin uselessly
                sessions = storage.get_json(_pool_key(pid), [])
                sessions.append({"theme": theme, "questions": qs})
                storage.set_json(_pool_key(pid), sessions)
        finally:
            with _refill_lock:
                _refilling.discard(pid)

    threading.Thread(target=_worker, daemon=True).start()


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
            return ai.grade_short_answer(q, answer)
        except Exception:
            pass
    expected = set(str(q["answer"]).lower().split())
    given = set(answer.lower().split())
    correct = len(expected & given) >= max(1, math.ceil(len(expected) * 0.2))
    return correct, q.get("explanation", "")


def answer_question(quest, answer):
    """Grade the next unanswered question, update the profile, return the
    reveal. Questions are strictly in order — the index is len(results)."""
    i = len(quest["results"])
    if i >= len(quest["questions"]):
        raise IndexError("quest already complete")
    q = quest["questions"][i]
    is_boss = i == len(quest["questions"]) - 1

    correct, feedback = _grade(q, answer)
    xp = config.XP_PER_CORRECT * (config.XP_BOSS_MULTIPLIER if is_boss else 1)

    p = get_player(quest["player_id"])
    if correct:
        quest["correct_count"] += 1
        quest["xp_gained"] += xp
        p["xp"] += xp
        if is_boss:
            p["boss_wins"] += 1
    profile_mod.record_answer(p, q["category"], correct)
    if q.get("id"):
        profile_mod.record_offline(p, q["id"], correct)
    save_player(p)

    quest["results"].append({"category": q["category"], "correct": correct})
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
        "player": public_player(p),
    }


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
