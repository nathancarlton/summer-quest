"""Pre-generated question pool.

Lets a quest start instantly: each pool entry is a full, themed, personalized
session generated ahead of time. A background thread tops the pool up while the
kid plays, so the slow reasoning-model call never sits in the critical path.

Storage: data/pool.jsonl, one JSON object per line: {"theme", "questions": [...]}.
"""
import json
import random
import threading

from . import ai, bank, config

POOL_PATH = config.DATA_DIR / "pool.jsonl"
TARGET_SESSIONS = 2  # ready-made quests to keep queued for future sessions

_lock = threading.Lock()        # guards pool-file read/modify/write in-process
_refilling = threading.Event()  # set while a background refill is in flight


def _read():
    if not POOL_PATH.exists():
        return []
    out = []
    for line in POOL_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass  # skip a corrupt line rather than lose the whole pool
    return out


def _write(sessions):
    POOL_PATH.write_text(
        "".join(json.dumps(s) + "\n" for s in sessions), encoding="utf-8"
    )


def session_count():
    with _lock:
        return len(_read())


def take_session():
    """Pop the questions of one ready session, or None if the pool is empty."""
    with _lock:
        sessions = _read()
        if not sessions:
            return None
        first = sessions.pop(0)
        _write(sessions)
    return first.get("questions", [])


def _add_session(theme, questions):
    with _lock:
        sessions = _read()
        sessions.append({"theme": theme, "questions": questions})
        _write(sessions)


def _fill(la_count, math_count, weak, prefs, target):
    """Generate themed sessions until the pool holds `target` of them.

    Blocking — run via refill_in_background. Each generated session is written
    as soon as it's ready, so progress survives the process exiting mid-fill.
    """
    threshold = max(3, (la_count + math_count) // 2)
    while session_count() < target:
        theme = random.choice(config.THEMES)
        try:
            qs = ai.generate_questions(la_count, math_count, weak,
                                       prefs=prefs, theme=theme)
        except Exception:
            return  # network/API problem — stop and try again next run
        qs = [q for q in qs if bank.valid_question(q)]
        if len(qs) < threshold:
            return  # a weak result; don't spin uselessly
        _add_session(theme, qs)


def refill_in_background(la_count, math_count, weak, prefs, target=TARGET_SESSIONS):
    """Kick off a daemon thread to top the pool up. No-op without an API key,
    if a refill is already running, or if the pool is already full."""
    if not config.MINIMAX_API_KEY:
        return
    # Claim the refill atomically so two callers can't both spawn a worker.
    with _lock:
        if _refilling.is_set() or len(_read()) >= target:
            return
        _refilling.set()

    def _worker():
        try:
            _fill(la_count, math_count, weak, prefs, target)
        finally:
            _refilling.clear()

    threading.Thread(target=_worker, daemon=True).start()
