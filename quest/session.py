"""The daily quest: fetch questions, run the loop, award XP, log, sync."""
import json
import math
from datetime import datetime, timezone

from . import ai, bank, config, profile as profile_mod, sync, ui


def _build_mix(n):
    la_count = round(n * config.LA_RATIO)
    return la_count, n - la_count


def _fetch_questions(p, n):
    la_count, math_count = _build_mix(n)
    prefs = p.get("prefs") or {}
    try:
        qs = ai.generate_questions(la_count, math_count,
                                   profile_mod.weak_categories(p), prefs=prefs)
        valid = [q for q in qs if _valid(q)]
        if len(valid) >= max(3, n // 2):
            if len(valid) < n:  # a batch fell short — top up from the bank
                off = p["offline"]
                valid += bank.sample(n - len(valid), la_count, off["mastered"], off["review"])
            return valid[:n], True
    except Exception:
        pass
    ui.console.print("[dim]⚠ AI unreachable — using offline question pack.[/]")
    # A couple of personalized questions up front, then fill from the bank.
    # Personalized questions are ephemeral (no id), so they can't collide with
    # the id-keyed bank questions.
    extras = [q for q in bank.personalized(prefs) if _valid(q)][:2]
    off = p["offline"]
    filler = bank.sample(n - len(extras), la_count, off["mastered"], off["review"])
    return (extras + filler)[:n], False


def _valid(q):
    if q.get("category") not in config.CATEGORIES:
        return False
    if q.get("type") not in ("mc", "short"):
        return False
    if not q.get("question") or not q.get("answer"):
        return False
    if q["type"] == "mc" and len(q.get("options") or []) != 4:
        return False
    return True


def _grade(q, answer, ai_available):
    if q["type"] == "mc":
        correct = answer.strip().upper()[:1] == str(q["answer"]).strip().upper()[:1]
        return correct, q.get("explanation", "")
    if ai_available:
        try:
            with ui.evaluating():  # spinner while the AI judges the written answer
                return ai.grade_short_answer(q, answer)
        except Exception:
            pass
    # Local fallback: keyword overlap with the model answer
    expected = set(str(q["answer"]).lower().split())
    given = set(answer.lower().split())
    correct = len(expected & given) >= max(1, math.ceil(len(expected) * 0.2))
    return correct, q.get("explanation", "")


def _log_history(entry):
    with config.HISTORY_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def run(p):
    streak_continued = profile_mod.update_streak(p)
    n = config.QUESTIONS_PER_SESSION
    ui.console.print("\n[cyan]Summoning today's quest...[/]")
    questions, ai_available = _fetch_questions(p, n)

    correct_count, xp_gained = 0, 0
    results = []
    for i, q in enumerate(questions, 1):
        is_boss = i == len(questions)
        answer = ui.ask_question(i, len(questions), q, is_boss)
        correct, feedback = _grade(q, answer, ai_available)
        xp = config.XP_PER_CORRECT * (config.XP_BOSS_MULTIPLIER if is_boss else 1)
        if correct:
            correct_count += 1
            xp_gained += xp
            p["xp"] += xp
            if is_boss:
                p["boss_wins"] += 1
        profile_mod.record_answer(p, q["category"], correct)
        if q.get("id"):  # offline-bank question — track mastery for spaced review
            profile_mod.record_offline(p, q["id"], correct)
        ui.show_result(correct, feedback, xp if correct else 0)
        results.append({"category": q["category"], "correct": correct})

    streak_bonus = config.XP_STREAK_BONUS * p["streak"] if streak_continued else 0
    p["xp"] += streak_bonus
    xp_gained += streak_bonus

    p["sessions_completed"] = p.get("sessions_completed", 0) + 1
    new_badges = profile_mod.check_badges(p, correct_count == len(questions))
    profile_mod.save(p)

    summary = {
        "player_id": p["id"],
        "player_name": p["name"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "score": correct_count,
        "total": len(questions),
        "xp_gained": xp_gained,
        "streak": p["streak"],
        "ai_powered": ai_available,
        "results": results,
    }
    _log_history(summary)

    ui.session_summary(
        p["name"], correct_count, len(questions), xp_gained, streak_bonus, new_badges
    )

    status = sync.push(p, summary)
    if status == "sent":
        ui.console.print("[dim]☁ Progress synced.[/]")
    elif status == "queued":
        ui.console.print("[dim]☁ Offline — progress queued for next sync.[/]")
