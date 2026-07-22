"""The daily quest: fetch questions, run the loop, award XP, log, sync."""
import json
import math
import random
from datetime import datetime, timezone

from . import ai, bank, config, pool, profile as profile_mod, sync, ui

_valid = bank.valid_question  # shared shape check


def _build_mix(n):
    la_count = round(n * config.LA_RATIO)
    return la_count, n - la_count


def prefetch(p):
    """Start (or top up) the background pool so future quests load instantly."""
    la_count, math_count = _build_mix(config.QUESTIONS_PER_SESSION)
    pool.refill_in_background(
        la_count, math_count, profile_mod.weak_categories(p),
        p.get("prefs") or {}, difficulty=p.get("difficulty", 2),
        subtopic_plan=profile_mod.subtopic_plan(p),
    )


def _finalize(p, prefs, questions, n, la_count):
    """Enforce the 'no repeats' rule for EVERY source (pool AI, bank, or
    personalized).

    Each question gets a content-hash id (question text + passage); any already
    mastered (answered correctly before) is dropped, dups are removed, and the
    set is topped up from the bank so a full quest of `n` still goes out.
    """
    off = p["offline"]
    mastered = set(off["mastered"])
    used, result = set(), []
    for q in questions:
        qid = q.get("id") or bank.question_id(q)
        q["id"] = qid
        if qid in mastered or qid in used:
            continue  # already aced, or a duplicate within this set
        used.add(qid)
        result.append(q)
    if len(result) < n:  # dropped some — refill with fresh, unmastered bank Qs
        for q in bank.sample(n - len(result), la_count, mastered | used, off["review"],
                             subtopic_plan=profile_mod.subtopic_plan(p)):
            if q["id"] not in used:
                used.add(q["id"])
                result.append(q)
    # Guarantee every MC option shows its A./B./C./D. letter (the AI omits them).
    return [bank.ensure_option_letters(q) for q in result[:n]]


def _offline_raw(p, prefs, n, la_count):
    """Bank questions, with a personalized cameo only sometimes — favorites
    are spice, not a staple."""
    extras = []
    if random.random() < 0.5:
        extras = [q for q in bank.personalized(prefs) if _valid(q)]
        random.shuffle(extras)
        extras = extras[:1]
    off = p["offline"]
    filler = bank.sample(n - len(extras), la_count, off["mastered"], off["review"],
                         subtopic_plan=profile_mod.subtopic_plan(p))
    return extras + filler


def _fetch_questions(p, n):
    la_count, math_count = _build_mix(n)
    prefs = p.get("prefs") or {}
    can_grade = bool(config.MINIMAX_API_KEY)

    # 1) Instant: a pre-generated themed session from the pool, if one is ready.
    pooled = pool.take_session()
    if pooled:
        valid = [q for q in pooled if _valid(q)]
        if len(valid) >= max(3, n // 2):
            prefetch(p)  # top the pool back up for next time
            return _finalize(p, prefs, valid, n, la_count), can_grade

    # 2) Pool not ready yet (first run): serve the personalized offline bank
    #    instantly, and brew AI quests in the background for next time.
    prefetch(p)
    if can_grade:
        ui.console.print(
            "[dim]✨ Today's quest is ready — fresh AI adventures are brewing "
            "in the background for next time.[/]"
        )
    else:
        ui.console.print("[dim]⚠ No API key — using the offline question pack.[/]")
    return _finalize(p, prefs, _offline_raw(p, prefs, n, la_count), n, la_count), can_grade


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
        profile_mod.record_answer(p, q["category"], correct, q.get("subtopic"))
        # Track mastery for every question so a correct one never returns.
        if q.get("id"):
            profile_mod.record_offline(p, q["id"], correct)
        ui.show_result(correct, feedback, xp if correct else 0)
        results.append({"category": q["category"], "correct": correct})

    streak_bonus = config.XP_STREAK_BONUS * p["streak"] if streak_continued else 0
    p["xp"] += streak_bonus
    xp_gained += streak_bonus

    p["sessions_completed"] = p.get("sessions_completed", 0) + 1
    new_badges = profile_mod.check_badges(p, correct_count == len(questions))
    difficulty_delta = profile_mod.adjust_difficulty(p, correct_count, len(questions))
    profile_mod.save(p)
    if difficulty_delta > 0:
        ui.console.print("[magenta]⬆ You're crushing it — tomorrow's questions level up![/]")
    elif difficulty_delta < 0:
        ui.console.print("[cyan]⬇ We'll ease things up a little tomorrow.[/]")

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
