"""MiniMax client (OpenAI-compatible chat completions).

Generates question sets and grades open-ended answers. All AI calls
degrade gracefully: on any failure, callers fall back to the offline bank
or local grading.
"""
import json
import random
import re
import threading

import requests

from . import config

TIMEOUT = 180
BATCH_SIZE = 3  # questions per request — smaller batches run concurrently,
#                 so the reasoning model's fixed think-time overlaps instead
#                 of stacking up into one very long serial call.


class AIUnavailable(Exception):
    pass


def _chat(messages, temperature=0.8, max_tokens=8000):
    if not config.MINIMAX_API_KEY:
        raise AIUnavailable("No MINIMAX_API_KEY set")
    resp = requests.post(
        f"{config.MINIMAX_BASE_URL.rstrip('/')}/chat/completions",
        headers={
            "Authorization": f"Bearer {config.MINIMAX_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": config.MINIMAX_MODEL,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    # Strip <think>...</think> blocks some MiniMax models emit, including an
    # unclosed block if the response was truncated mid-thought.
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
    content = re.sub(r"<think>.*$", "", content, flags=re.DOTALL)
    return content.strip()


def _extract_json(text):
    text = re.sub(r"```(?:json)?|```", "", text).strip()
    start = min((i for i in (text.find("["), text.find("{")) if i != -1), default=-1)
    if start == -1:
        raise ValueError("No JSON found in AI response")
    return json.loads(text[start:])


GEN_SYSTEM = """You create engaging practice questions for a student entering \
{grade}. Tone: fun, adventurous, encouraging — like a quest game. \
Never say where things appear on screen (no "below", "above", "following", \
"to the right"); the layout varies, so write "this sentence" or "the passage". \
Return ONLY a JSON array, no prose, no markdown fences."""

# {theme} is shared across every batch in a session so the whole quest feels
# like one little world; {favorites} folds in the kid's stated interests.
GEN_LA_PROMPT = """Create {n} language arts questions targeting Minnesota MCA \
reading/language skills, drawn from these categories: vocabulary, grammar, \
reading, figurative_language, writing_mechanics.
Emphasize these weaker skills where they fit: {weak}.

Weave everything into ONE fun setting: {theme}. {favorites} Let details recur \
so it feels like a connected story world, not random trivia.

At least one question should be type "short" (a one-sentence written answer). \
Short-answer tasks must be PRECISELY gradable: state exactly what to produce, \
and never ask for something with no correct form (e.g., a list needs THREE OR \
MORE items to demonstrate commas — never ask for "two items in a list").
For any "reading" question, include a 3-5 sentence original passage in "passage".

Each JSON object:
{{"category": "vocabulary|grammar|reading|figurative_language|writing_mechanics", \
"type": "mc"|"short", "question": "...", \
"passage": "..." or null, "options": ["A...","B...","C...","D..."] or null, \
"answer": "correct option letter or model short answer", \
"explanation": "kid-friendly why"}}"""

GEN_MATH_PROMPT = """Create {n} genuinely hard math_challenge word problems for \
a strong math student: ratios, rates, percentages, pre-algebra, multi-step logic.

Set the problems in ONE fun world: {theme}. {favorites} Keep the numbers real \
and the scenarios vivid.

Each must be type "mc" with exactly 4 options. Each JSON object:
{{"category": "math_challenge", "type": "mc", "question": "...", \
"passage": null, "options": ["A...","B...","C...","D..."], \
"answer": "correct option letter", "explanation": "kid-friendly worked solution"}}"""


GEN_EXPEDITION_PROMPT = """Create {n} fun multiple-choice TRIVIA questions for a \
curious student about {topic}: {desc}.
Mix jaw-dropping "whoa, really?!" facts with genuinely useful knowledge.
ACCURACY MATTERS: use only facts you are certain of. For numbers that change \
over time (populations, company values, store counts), say "about" and make \
the answer choices far apart.
SAFETY: chemicals, venom, and health topics must be framed as safety knowledge \
(what to avoid and WHY) — never include instructions for making or doing \
anything dangerous.

Each must be type "mc" with exactly 4 options. Each JSON object:
{{"category": "{key}", "type": "mc", "question": "...", "passage": null, \
"options": ["A...","B...","C...","D..."], "answer": "correct option letter", \
"explanation": "kid-friendly why, with the wow factor"}}"""


def generate_expedition(topic_key, topic_label, topic_desc, n=5):
    """Generate one expedition's trivia set — a single small batch."""
    return _gen_batch(GEN_EXPEDITION_PROMPT.format(
        n=n, topic=topic_label, desc=topic_desc, key=topic_key
    ))


def _chunks(total, size):
    """Split a count into batch sizes, e.g. _chunks(7, 3) -> [3, 3, 1]."""
    return [min(size, total - i) for i in range(0, total, size)]


def _parallel_map(fn, items):
    """Run fn over items on daemon threads and collect results in order.

    Deliberately NOT ThreadPoolExecutor: its atexit hook joins worker threads
    on interpreter exit, which would hang a quit while a background refill has
    an AI request in flight. Daemon threads are simply dropped on exit.
    """
    results = [None] * len(items)

    def _run(i, item):
        results[i] = fn(item)

    threads = [threading.Thread(target=_run, args=(i, item), daemon=True)
               for i, item in enumerate(items)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


# Safety net for spatial references that slip past the prompt: "read the
# sentence below" -> "read the sentence". Anchored to a content noun so it
# won't touch legitimate math like "temperatures below zero".
_SPATIAL_RE = re.compile(
    r"\b(sentence|passage|paragraph|text|story|poem|words?|excerpt)\s+"
    r"(?:down\s+below|below|above)\b",
    re.IGNORECASE,
)


def _sanitize(q):
    for field in ("question", "explanation"):
        if isinstance(q.get(field), str):
            q[field] = _SPATIAL_RE.sub(r"\1", q[field])
    return q


def _gen_batch(prompt):
    text = _chat(
        [
            {"role": "system", "content": GEN_SYSTEM.format(grade=config.GRADE_LEVEL)},
            {"role": "user", "content": prompt},
        ]
    )
    data = _extract_json(text)
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ValueError("AI returned unexpected shape")
    return [_sanitize(q) for q in data if isinstance(q, dict)]


# How each stored favorite reads inside the prompt. Keys line up with the
# badge-bonus questions in the web app — deliberately impersonal (things,
# places, weather — never people).
_PREF_PHRASES = {
    "animal": "their favorite animal, a {v}",
    "food": "their favorite food, {v}",
    "theme": "their favorite adventure world, {v}",
    "color": "their favorite color, {v}",
    "place": "a place they dream of visiting, {v}",
    "instrument": "an instrument they like, the {v}",
    "sport": "a sport or activity they enjoy, {v}",
    "song": 'a song they love, "{v}"',
    "weather": "their favorite kind of weather, {v}",
}


def _favorites_line(prefs):
    """A sentence telling the model which favorites to work in (or empty).

    Rotates through at most 3 per generation so a kid with many favorites
    gets different combinations threaded into different sessions."""
    prefs = prefs or {}
    bits = [_PREF_PHRASES[k].format(v=v) for k, v in prefs.items()
            if v and k in _PREF_PHRASES]
    if not bits:
        return ""
    if len(bits) > 3:
        bits = random.sample(bits, 3)
    return f"Delight the student by working in their favorites: {'; '.join(bits)}."


# Adaptive challenge: the level (profile['difficulty']) picks the note that
# steers question difficulty in both generation prompts.
DIFFICULTY_NOTES = {
    1: "Difficulty: gentle and confidence-building, around mid-5th-grade level. "
       "Simple vocabulary, single-step problems, friendly distractors.",
    2: "Difficulty: standard for a student entering 6th grade.",
    3: "Difficulty: slightly advanced, end-of-6th-grade level — include some "
       "multi-step thinking.",
    4: "Difficulty: challenging, 7th-grade level — multi-step reasoning and "
       "subtler answer choices.",
    5: "Difficulty: very challenging, 8th-grade level — every question should "
       "require real reasoning, with distractors that catch common mistakes.",
}


def generate_questions(la_count, math_count, weak_categories, prefs=None, theme=None,
                       difficulty=None):
    """Generate a full question set via several small concurrent requests.

    Batching keeps each call short so the reasoning model's think-time runs
    in parallel; a single 10-question call takes ~2.5 min, batched ~1 min.
    One shared `theme` threads through every batch for a coherent world;
    `difficulty` (1-5) steers how hard the questions get.
    Partial results are fine — the caller validates and falls back if short.
    """
    weak = ", ".join(weak_categories) if weak_categories else "none identified yet"
    theme = theme or random.choice(config.THEMES)
    favorites = _favorites_line(prefs)
    level_note = "\n" + DIFFICULTY_NOTES.get(difficulty or 2, DIFFICULTY_NOTES[2])
    prompts = [GEN_LA_PROMPT.format(n=c, weak=weak, theme=theme, favorites=favorites)
               + level_note
               for c in _chunks(la_count, BATCH_SIZE)]
    prompts += [GEN_MATH_PROMPT.format(n=c, theme=theme, favorites=favorites)
                + level_note
                for c in _chunks(math_count, BATCH_SIZE)]

    questions = []
    for result in _parallel_map(_safe_batch, prompts):
        questions.extend(result or [])
    if not questions:
        raise ValueError("AI returned no questions")
    return questions


def _safe_batch(prompt):
    """Run one batch, swallowing its error so one slow/failed call doesn't
    sink the whole set — we return what the other batches produced."""
    try:
        return _gen_batch(prompt)
    except Exception:
        return []


# Writing/mechanics answers are graded exactly; meaning-based answers generously.
_MECHANICS = {"writing_mechanics", "grammar"}

_RUBRIC_EXACT = (
    "This is a WRITING-MECHANICS task. Compare the student's answer to the model "
    "word by word. Check capitalization, punctuation, spelling, AND every word — "
    "a missing or changed word (like a dropped 'the') is an error. Mark correct=true "
    "ONLY if all mechanics and wording are right; otherwise correct=false."
)
_RUBRIC_MEANING = (
    "Grade generously on MEANING — accept reasonable paraphrases and partial "
    "understanding. Focus on whether the idea is right, not exact wording."
)

GRADE_PROMPT = """A {grade} student answered a practice question. Category: {category}.

Question: {question}
{passage_block}Model answer: {expected}
Student's answer: {student}

{rubric}

Read the student's answer CAREFULLY and completely — do not overlook any mistake. \
Be warm and encouraging, but honest: name EVERY specific fix needed so nothing \
slips by (if you say "great job", still list what's wrong).
First sanity-check the QUESTION itself: if it is ambiguous or flawed and the \
student's answer is a reasonable reading of it, give the student the benefit of \
the doubt and mark correct=true.
Return ONLY JSON: {{"correct": true|false, "feedback": "2-3 encouraging, specific \
sentences that celebrate what's right and clearly point out each thing to fix."}}"""


CHALLENGE_PROMPT = """A {grade} student has CHALLENGED the grading of a practice \
question. You are the independent appeals judge. Re-evaluate from scratch, fairly \
and rigorously — the original grader may have been wrong, and the QUESTION ITSELF \
may be flawed or ambiguous. If the question is flawed, or the student's answer is \
a defensible reading of it, rule FOR the student.

Question: {question}
{passage_block}{options_block}Official answer: {expected}
Student's answer: {student}
Feedback the student received: {feedback}

Return ONLY JSON: {{"student_is_right": true|false, "message": "2-3 kid-friendly \
sentences delivering the ruling honestly — celebrate an overturn; if upheld, \
explain kindly and clearly why the original ruling stands."}}"""


def challenge_grading(question, student_answer, original_feedback=""):
    """Adversarial re-review of a disputed ruling. Returns (overturned, message)."""
    passage_block = (
        f"Passage: {question['passage']}\n" if question.get("passage") else ""
    )
    options_block = (
        "Options:\n" + "\n".join(question["options"]) + "\n"
        if question.get("options") else ""
    )
    text = _chat(
        [
            {
                "role": "user",
                "content": CHALLENGE_PROMPT.format(
                    grade=config.GRADE_LEVEL,
                    question=question["question"],
                    passage_block=passage_block,
                    options_block=options_block,
                    expected=question["answer"],
                    student=student_answer,
                    feedback=original_feedback or "(none recorded)",
                ),
            }
        ],
        temperature=0.2,
        max_tokens=3000,
    )
    result = _extract_json(text)
    return bool(result.get("student_is_right")), result.get("message", "")


def grade_short_answer(question, student_answer):
    passage_block = (
        f"Passage: {question['passage']}\n" if question.get("passage") else ""
    )
    category = question.get("category", "")
    rubric = _RUBRIC_EXACT if category in _MECHANICS else _RUBRIC_MEANING
    text = _chat(
        [
            {
                "role": "user",
                "content": GRADE_PROMPT.format(
                    grade=config.GRADE_LEVEL,
                    category=category or "short answer",
                    question=question["question"],
                    passage_block=passage_block,
                    expected=question["answer"],
                    student=student_answer,
                    rubric=rubric,
                ),
            }
        ],
        temperature=0.2,
        max_tokens=3000,
    )
    result = _extract_json(text)
    return bool(result.get("correct")), result.get("feedback", "")
