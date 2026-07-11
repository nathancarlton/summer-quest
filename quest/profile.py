"""Player profile: XP, levels, streaks, badges, per-category accuracy."""
import json
import uuid
from datetime import date, timedelta

from . import config

BADGES = {
    "first_quest": ("🗺️  First Quest", "Complete your first session"),
    "rising_star": ("🌱 Rising Star", "Complete your second quest"),
    "getting_serious": ("🚀 Getting Serious", "Complete 5 quests"),
    "streak_3": ("🔥 On Fire", "3-day streak"),
    "streak_7": ("⚡ Unstoppable", "7-day streak"),
    "streak_14": ("🌟 Legend in Training", "14-day streak"),
    "perfect": ("💯 Flawless", "Perfect session"),
    "boss_slayer": ("⚔️  Boss Slayer", "Beat 5 boss questions"),
    "wordsmith": ("📚 Wordsmith", "50 language arts questions correct"),
    "mathlete": ("🧮 Mathlete", "25 math challenges correct"),
    "centurion": ("🏛️  Centurion", "Answer 100 questions"),
}


def _default(name):
    return {
        "id": str(uuid.uuid4()),
        "name": name,
        "xp": 0,
        "streak": 0,
        "last_played": None,
        "badges": [],
        "boss_wins": 0,
        "sessions_completed": 0,
        "totals": {"answered": 0, "correct": 0, "la_correct": 0, "math_correct": 0},
        "categories": {c: {"answered": 0, "correct": 0} for c in config.CATEGORIES},
        # Offline mastery: `mastered` = answered correctly (never re-asked);
        # `review` = missed, due to reappear in a future session until correct.
        "offline": {"mastered": [], "review": []},
    }


def load():
    if config.PROFILE_PATH.exists():
        p = json.loads(config.PROFILE_PATH.read_text(encoding="utf-8"))
        for c in config.CATEGORIES:  # forward-compat for new categories
            p["categories"].setdefault(c, {"answered": 0, "correct": 0})
        p.setdefault("sessions_completed", 0)  # forward-compat for older profiles
        p.setdefault("offline", {"mastered": [], "review": []})
        return p
    return None


def save(profile):
    config.PROFILE_PATH.write_text(
        json.dumps(profile, indent=2), encoding="utf-8"
    )


def create(name):
    p = _default(name)
    save(p)
    return p


def level_info(xp):
    current = config.LEVELS[0]
    nxt = None
    for threshold, title in config.LEVELS:
        if xp >= threshold:
            current = (threshold, title)
        elif nxt is None:
            nxt = (threshold, title)
    num = config.LEVELS.index(current) + 1
    return num, current[1], nxt


def update_streak(profile):
    """Call at session start. Returns True if streak continued/started today."""
    today = date.today().isoformat()
    last = profile["last_played"]
    if last == today:
        return False  # already played today; streak unchanged
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    profile["streak"] = profile["streak"] + 1 if last == yesterday else 1
    profile["last_played"] = today
    return True


def record_answer(profile, category, correct):
    profile["totals"]["answered"] += 1
    cat = profile["categories"][category]
    cat["answered"] += 1
    if correct:
        profile["totals"]["correct"] += 1
        cat["correct"] += 1
        key = "math_correct" if config.CATEGORIES[category] == "math" else "la_correct"
        profile["totals"][key] += 1


def record_offline(profile, qid, correct):
    """Track mastery of an offline-bank question so it isn't re-asked once
    answered correctly, and is queued for review if missed."""
    off = profile["offline"]
    if correct:
        if qid not in off["mastered"]:
            off["mastered"].append(qid)
        if qid in off["review"]:
            off["review"].remove(qid)
    elif qid not in off["mastered"] and qid not in off["review"]:
        off["review"].append(qid)


def weak_categories(profile, k=2):
    """Lowest-accuracy LA categories with at least 3 attempts."""
    scored = []
    for cat, s in profile["categories"].items():
        if config.CATEGORIES[cat] == "la" and s["answered"] >= 3:
            scored.append((s["correct"] / s["answered"], cat))
    scored.sort()
    return [c for _, c in scored[:k]]


def check_badges(profile, session_perfect):
    """Returns list of newly earned badge keys."""
    t = profile["totals"]
    sessions = profile.get("sessions_completed", 0)
    earned = []
    checks = {
        "first_quest": sessions >= 1,
        "rising_star": sessions >= 2,
        "getting_serious": sessions >= 5,
        "streak_3": profile["streak"] >= 3,
        "streak_7": profile["streak"] >= 7,
        "streak_14": profile["streak"] >= 14,
        "perfect": session_perfect,
        "boss_slayer": profile["boss_wins"] >= 5,
        "wordsmith": t["la_correct"] >= 50,
        "mathlete": t["math_correct"] >= 25,
        "centurion": t["answered"] >= 100,
    }
    for key, ok in checks.items():
        if ok and key not in profile["badges"]:
            profile["badges"].append(key)
            earned.append(key)
    return earned
