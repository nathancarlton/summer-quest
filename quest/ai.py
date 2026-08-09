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

from . import bank, config

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
Avoid overused fantasy clichés: NO dragons, wizards, or enchanted castles \
unless the given theme explicitly features them — real-world wonder (science, \
sports, animals, inventions, weird history) beats recycled fantasy. \
Never say where things appear on screen (no "below", "above", "following", \
"to the right"); the layout varies, so write "this sentence" or "the passage". \
Return ONLY a JSON array, no prose, no markdown fences."""

# {theme} is shared across every batch in a session so the whole quest feels
# like one little world; {favorites} folds in the kid's stated interests.
GEN_LA_PROMPT = """Create {n} language arts questions targeting Minnesota MCA \
reading/language skills, drawn from these categories: vocabulary, grammar, \
reading, figurative_language, writing_mechanics.
Emphasize these weaker skills where they fit: {weak}.

Set the questions loosely in this world: {theme} — but VARY the characters, \
subjects, and scenarios from question to question; never reuse the same \
animal, object, or person across multiple questions. Draw on the wide range \
of things curious 11-12-year-olds find genuinely cool: space, inventions, \
weird history, ocean creatures, sports moments, music, video games, food \
trucks, natural disasters, mysteries, record-breaking feats. {favorites}

NO LENGTH TELLS: never let the correct option be recognizably the longest or \
most detailed — keep options similar in length, and sometimes make a wrong \
option the longest one.
At least one question should be type "short" (a one-sentence written answer). \
Short-answer tasks must be PRECISELY gradable: state exactly what to produce, \
and never ask for something with no correct form (e.g., a list needs THREE OR \
MORE items to demonstrate commas — never ask for "two items in a list"). \
When the task asks the student to supply their own examples (any "write three \
…", "use it in a sentence"), the question must name every requirement being \
graded (how many items, what kind, the punctuation to use), because "answer" \
can only be a SAMPLE response there — countless different answers are equally \
correct, and the student will not reproduce yours.
For any "reading" question, include a 3-5 sentence original passage in "passage".

Each JSON object:
{{"category": "vocabulary|grammar|reading|figurative_language|writing_mechanics", \
"type": "mc"|"short", "subtopic": "see the subtopic rule, else null", \
"question": "...", \
"passage": "..." or null, "options": ["A...","B...","C...","D..."] or null, \
"answer": "correct option letter or model short answer", \
"explanation": "kid-friendly why"}}"""

GEN_MATH_PROMPT = """Create {n} genuinely hard math_challenge word problems for \
a strong math student — the exact skills to cover come from the subtopic rule \
at the end of this prompt.

Set the problems loosely in this world: {theme} — but give each problem its \
own fresh scenario and cast; never reuse the same animal, object, or person \
across problems. Pull scenarios from things 11-12-year-olds actually care \
about: games, sports stats, building things, saving up for stuff, wild \
nature facts, space missions. {favorites} Keep the numbers real and the \
scenarios vivid.

CRITICAL — before writing each JSON object, SOLVE the problem yourself completely:
- The correct result must be a whole number whenever the story implies one \
(you can't have half a gem or 7.5 people).
- The correct result MUST be one of the four options, and "answer" must be its letter.
- The explanation must be one clean worked solution. If you notice any \
inconsistency while solving, FIX the problem and re-solve — never mention the \
inconsistency or adjust the story to excuse it.

Each must be type "mc" with exactly 4 options. Each JSON object:
{{"category": "math_challenge", "type": "mc", \
"subtopic": "see the subtopic rule", "question": "...", \
"passage": null, "options": ["A...","B...","C...","D..."], \
"answer": "correct option letter", "explanation": "kid-friendly worked solution"}}"""


GEN_EXPEDITION_PROMPT = """Create {n} fun multiple-choice TRIVIA questions for a \
curious student about {topic}: {desc}.
Mix jaw-dropping "whoa, really?!" facts with genuinely useful knowledge.
NO LENGTH TELLS: the correct option must NOT be recognizably the longest or \
most detailed one. Keep all four options about the same length, and often make \
a WRONG option the longest and most detailed-sounding. Save explanations for \
the "explanation" field — the correct option itself should be short and plain.
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


READING_QUIZ_PROMPT = """A student just finished reading a chapter of "{title}" \
by {author}. Create exactly {n} multiple-choice comprehension questions about \
THIS chapter only — what happened, why characters did what they did, and what a \
word or phrase means in context. Use ONLY facts from the chapter text below; \
never spoil events beyond it.
NO LENGTH TELLS: keep all four options similar in length; often make a wrong \
option the most detailed-sounding one.

Each must be type "mc" with exactly 4 options. Each JSON object:
{{"category": "reading", "type": "mc", "question": "...", "passage": null, \
"options": ["A...","B...","C...","D..."], "answer": "correct option letter", \
"explanation": "kid-friendly why, pointing to the moment in the chapter"}}

Chapter text:
{text}"""


def generate_reading_quiz(title, author, chapter_text, n=3):
    """Comprehension questions grounded in the exact chapter the kid read.
    Runs through the same confusion + length-tell filters as everything else."""
    return _gen_batch(READING_QUIZ_PROMPT.format(
        title=title, author=author, n=n, text=chapter_text[:24000]
    ))


def generate_expedition(topic_key, topic_label, topic_desc, n=5):
    """Generate one expedition's trivia set — a single small batch, then the
    same adversarial answer-key audit the daily quests get."""
    return verify_mc(_gen_batch(GEN_EXPEDITION_PROMPT.format(
        n=n, topic=topic_label, desc=topic_desc, key=topic_key
    )))


def looks_confused(q):
    """Public alias — the serve-gate sweeper uses this on stored questions."""
    return _looks_confused(q)


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


# A model that catches its own mistake mid-explanation ("wait, that's not an
# option! ...the dragon secretly added some!") has produced a broken question.
# These tells in the EXPLANATION are grounds for automatic rejection.
_CONFUSED_RE = re.compile(
    r"not an option|let me (check|reconsider|recalculate|re-?solve|try)|"
    r"check(ing)? again|can'?t be right|doesn'?t (work|add up|match)|"
    r"i made (an error|a mistake)|hmm|secretly (add|remov|hid)|"
    r"wait[,—: ]|that'?s (odd|strange|wrong)",
    re.IGNORECASE,
)


def _looks_confused(q):
    return bool(_CONFUSED_RE.search(str(q.get("explanation") or "")))


def _length_tell(q):
    """True when the correct MC option is so much longer than every other
    option that its length gives the answer away — a known habit of
    generated questions ('the thorough-sounding one is right')."""
    if q.get("type") != "mc" or not q.get("options"):
        return False
    letter = str(q.get("answer", "")).strip()[:1].upper()
    idx = "ABCD".find(letter)
    if idx == -1 or idx >= len(q["options"]):
        return False
    strip = lambda o: re.sub(r"^\s*[A-Da-d][.):]\s*", "", str(o)).strip()
    correct_len = len(strip(q["options"][idx]))
    others = [len(strip(o)) for i, o in enumerate(q["options"]) if i != idx]
    return correct_len > 25 and correct_len > 1.5 * max(others)


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
    return [_sanitize(q) for q in data
            if isinstance(q, dict) and not _looks_confused(q)
            and not _length_tell(q)]


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
    """Favorites are SPICE, not a staple: half of all batches get no
    favorites at all, and the rest are told to nod to at most one or two —
    a kid who loves panthers should be delighted by an occasional panther
    cameo, not stalked by one through every question."""
    prefs = prefs or {}
    bits = [_PREF_PHRASES[k].format(v=v) for k, v in prefs.items()
            if v and k in _PREF_PHRASES]
    if not bits or random.random() < 0.5:
        return ""
    picked = random.sample(bits, min(len(bits), random.choice([1, 2])))
    return (
        "As a small treat, AT MOST one or two questions may subtly nod to "
        f"{'; '.join(picked)} — every other question must be about something "
        "completely different."
    )


# Subtopic balancing: left unsteered, the model collapses onto the most
# prototypical concepts (audits of the live pool found 19 of 20 figurative-
# language questions were simile/metaphor). Each batch gets an explicit
# rotation, least-practiced-first for THIS learner; offsetting it by how many
# questions earlier batches consumed keeps concurrent batches from all
# opening with the same subtopic.
_TRACKED_LA = [c for c in config.SUBTOPICS if config.CATEGORIES.get(c) == "la"]
_TRACKED_MATH = [c for c in config.SUBTOPICS if config.CATEGORIES.get(c) == "math"]


def _subtopic_note(subtopic_plan, categories, offset):
    lines = []
    for cat in categories:
        subs = (subtopic_plan or {}).get(cat) or config.SUBTOPICS.get(cat)
        if not subs:
            continue
        rot = [subs[(offset + i) % len(subs)] for i in range(len(subs))]
        lines.append(
            f"\nSUBTOPIC RULE for {cat}: each {cat} question must drill exactly "
            f"ONE of these subtopics, working through them in this order "
            f"(earliest first — this learner has practiced those least): "
            f"{', '.join(rot)}. Never give two questions in this set the same "
            f'subtopic, and record your choice in the "subtopic" field.'
        )
    return "".join(lines)


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
                       difficulty=None, subtopic_plan=None):
    """Generate a full question set via several small concurrent requests.

    Batching keeps each call short so the reasoning model's think-time runs
    in parallel; a single 10-question call takes ~2.5 min, batched ~1 min.
    One shared `theme` threads through every batch for a coherent world;
    `difficulty` (1-5) steers how hard the questions get; `subtopic_plan`
    (profile.subtopic_plan) rotates tracked categories through their
    least-practiced subtopics so coverage stays even per learner.
    Partial results are fine — the caller validates and falls back if short.
    """
    weak = ", ".join(weak_categories) if weak_categories else "none identified yet"
    theme = theme or random.choice(config.THEMES)
    favorites = _favorites_line(prefs)
    level_note = "\n" + DIFFICULTY_NOTES.get(difficulty or 2, DIFFICULTY_NOTES[2])
    prompts = [GEN_LA_PROMPT.format(n=c, weak=weak, theme=theme, favorites=favorites)
               + level_note + _subtopic_note(subtopic_plan, _TRACKED_LA, i)
               for i, c in enumerate(_chunks(la_count, BATCH_SIZE))]
    consumed = 0
    for c in _chunks(math_count, BATCH_SIZE):
        prompts.append(GEN_MATH_PROMPT.format(n=c, theme=theme, favorites=favorites)
                       + level_note
                       + _subtopic_note(subtopic_plan, _TRACKED_MATH, consumed))
        consumed += c

    questions = []
    for result in _parallel_map(_safe_batch, prompts):
        questions.extend(result or [])
    if not questions:
        raise ValueError("AI returned no questions")
    return verify_mc([bank.tag_subtopic(q) for q in questions])


MC_VERIFY_PROMPT = """You are auditing the answer keys of multiple-choice practice \
questions (math, language arts, and trivia). For EACH question, determine the \
correct answer YOURSELF first — solve math step by step, work through grammar and \
reading carefully, recall facts precisely — and only then judge the official letter.
A question is BAD if: the true answer is not among the options, the official \
letter points at the wrong option, more than one option is defensibly correct, \
the story forces impossible values (like a fraction of a physical object), or \
the question is unanswerable as written.

Questions (JSON): {problems}

Return ONLY a JSON array, one entry per question, same order:
[{{"i": 0, "your_answer": "B", "official_is_correct": true}}, ...]"""


def verify_mc(questions):
    """Adversarial answer-key audit for multiple-choice questions. An
    independent pass re-derives each answer; questions whose key fails are
    dropped. Runs only in background brewing/sweeping, so the extra call
    costs no kid-time. If the audit call itself fails, questions pass
    through unaudited — availability beats perfection."""
    idxs = [i for i, q in enumerate(questions)
            if q.get("type") == "mc" and q.get("options")]
    if not idxs:
        return questions
    payload = []
    for n, i in enumerate(idxs):
        q = questions[i]
        item = {"i": n, "question": q["question"], "options": q["options"],
                "official_answer": str(q["answer"])}
        if q.get("passage"):
            item["passage"] = q["passage"]
        payload.append(item)
    try:
        text = _chat(
            [{"role": "user",
              "content": MC_VERIFY_PROMPT.format(problems=json.dumps(payload))}],
            temperature=0.0,
            max_tokens=8000,
        )
        verdicts = _extract_json(text)
        bad = {idxs[v["i"]] for v in verdicts
               if isinstance(v, dict) and not v.get("official_is_correct", True)
               and 0 <= v.get("i", -1) < len(idxs)}
    except Exception:
        return questions
    return [q for i, q in enumerate(questions) if i not in bad]


def _safe_batch(prompt):
    """Run one batch, swallowing its error so one slow/failed call doesn't
    sink the whole set — we return what the other batches produced."""
    try:
        return _gen_batch(prompt)
    except Exception:
        return []


# Writing/mechanics answers are graded exactly; meaning-based answers generously.
_MECHANICS = {"writing_mechanics", "grammar"}

# OPEN-ENDED tasks ask the learner to invent their own content ("write three
# kinds of space objects", "write a sentence using 'brave'"). The stored answer
# is then just ONE valid sample, and grading against it word-by-word marks
# perfectly good answers wrong — which is exactly what happened to a comma
# task whose sample read "planets, moons, and asteroids": a learner who wrote
# "a star, a planet, and a moon" was told to swap in the sample's nouns.
# "Rewrite…" deliberately does NOT match (\b won't fire mid-word) — rewriting a
# given sentence has one right answer.
_OPEN_ENDED_RE = re.compile(
    r"\b(?:write|list|name|give|provide|share|think of|come up with)\b[^.?!]{0,60}"
    r"\b(?:two|three|four|five|2|3|4|5|a few|several|some)\b"
    r"|\b(?:write|give|name|list|come up with)\b[^.?!]{0,30}"
    r"\b(?:an?|one|your)\s+(?:own\s+)?(?:example|sentence|word|idea|phrase|reason)"
    r"|\byour own\b",
    re.IGNORECASE,
)


def _is_open_ended(question_text):
    """True when the learner supplies the content, so the stored answer is one
    acceptable response rather than the target."""
    return bool(_OPEN_ENDED_RE.search(question_text or ""))


# How many items the task asked for ("three or more pizza toppings").
_ASK_COUNT_RE = re.compile(
    r"\b(?:write|list|name|give|provide|share|think of|come up with)\b[^.?!]{0,60}?"
    r"\b(two|three|four|five|2|3|4|5)\b(\s+or\s+more)?",
    re.IGNORECASE,
)
_WORD_NUMBERS = {"two": 2, "three": 3, "four": 4, "five": 5,
                 "2": 2, "3": 3, "4": 4, "5": 5}


def _asked_count(question_text):
    """(minimum items, or_more) the question demands, or (None, False)."""
    m = _ASK_COUNT_RE.search(question_text or "")
    if not m:
        return None, False
    return _WORD_NUMBERS.get(m.group(1).lower()), bool(m.group(2))


def _itemize(student_answer):
    """Split a written list into its items. Counting is the one part of this
    job a language model reliably gets wrong — a learner who wrote
    'Pepperoni, cheese ,and sosage' was told they had listed only two — so we
    do it in code and hand the grader the count as a fact.

    Splitting on "and" can over-count a compound item ("bacon and eggs, toast,
    juice" reads as four). That errs toward crediting the learner, which is the
    right direction to be wrong in on a task this open-ended."""
    parts = re.split(r",|\band\b|;", student_answer or "")
    items = []
    for part in parts:
        # Drop a leading sentence frame ("She could find a star" -> "a star").
        part = re.sub(r"^\s*(?:[A-Za-z' ]{0,40}?\b(?:find|study|see|use|are|is|be|"
                      r"include|pack|choose|pick)\b)\s*", "", part.strip(), count=1,
                      flags=re.IGNORECASE)
        part = part.strip(" .!?\"'")
        if part:
            items.append(part)
    return items


_RUBRIC_EXACT = (
    "This is a WRITING-MECHANICS task with ONE correct form. Compare the student's "
    "answer to the model word by word. Check capitalization, punctuation, spelling, "
    "AND every word — a missing or changed word (like a dropped 'the') is an error. "
    "Mark correct=true ONLY if all mechanics and wording are right; otherwise "
    "correct=false."
)
_RUBRIC_MEANING = (
    "Grade generously on MEANING — accept reasonable paraphrases and partial "
    "understanding. Focus on whether the idea is right, not exact wording."
)
_RUBRIC_OPEN_MECHANICS = (
    "This task asks the student to INVENT their own content and present it in a "
    "particular form. The answer on file is ONE possible response; the student's "
    "items will be different, and that is exactly what should happen — an item it "
    "does not contain is not an error, and an item it contains that the student "
    "omitted is not a missing answer.\n"
    "Mark correct=true when the student's list has enough items of the right kind "
    "and its punctuation is right. What counts as an error: a misspelled word the "
    "student wrote; a missing comma between items; a space before a comma; too few "
    "items. What is NOT an error: different items than the ones on file; the serial "
    "comma style \"a, b, and c\" (both that and \"a, b, c\" are correct); capitalizing "
    "the first word of an answer; a natural sentence frame such as \"She could find "
    "a star, a planet, and a moon\"."
)
_RUBRIC_OPEN_MEANING = (
    "This task asks the student to INVENT their own content. The model answer is ONE "
    "sample among many correct ones. Judge only whether the student's answer does "
    "what the question asked (the right number of items, of the right kind, sensible "
    "for the topic). Never require it to match the model."
)

GRADE_PROMPT = """A {grade} student answered a practice question. Category: {category}.

Question: {question}
{passage_block}{answer_label}{expected}
Student's answer: {student}
{item_check}
{rubric}

The student never sees the answer on file, so your feedback must NEVER mention \
"the model", "the model answer", "the official answer", the format it uses, or \
anything it happens to contain. Talk only about the student's own answer and what \
the question asked for.

Read the student's answer CAREFULLY and completely — do not overlook any mistake. \
Be warm and encouraging, but honest: name EVERY specific fix needed so nothing \
slips by (if you say "great job", still list what's wrong).
First sanity-check the QUESTION itself: if it is ambiguous or flawed and the \
student's answer is a reasonable reading of it, give the student the benefit of \
the doubt and mark correct=true.
If the student's answer does everything the question asked for, mark correct=true \
even when it looks nothing like the answer on file, and never tell a student to \
change a correct answer so it matches that one.
Return ONLY JSON: {{"correct": true|false, "feedback": "2-3 encouraging, specific \
sentences that celebrate what's right and clearly point out each thing to fix."}}"""


CHALLENGE_PROMPT = """A {grade} student has CHALLENGED the grading of a practice \
question. You are the independent appeals judge. Re-evaluate from scratch, fairly \
and rigorously — the original grader may have been wrong, and the QUESTION ITSELF \
may be flawed or ambiguous. If the question is flawed, or the student's answer is \
a defensible reading of it, rule FOR the student.

Question: {question}
{passage_block}{options_block}{answer_label}{expected}
Student's answer: {student}
Feedback the student received: {feedback}

Return ONLY JSON: {{"student_is_right": true|false, "message": "2-3 kid-friendly \
sentences delivering the ruling honestly — celebrate an overturn; if upheld, \
explain kindly and clearly why the original ruling stands."}}"""


MC_CHALLENGE_PROMPT = """A {grade} student challenged a multiple-choice question. \
Multiple-choice answers are checked by exact letter match in code, so there is no \
grader to have made a mistake here: the ONLY question is whether the answer key \
itself is wrong. You are auditing the key.

Work out the correct answer YOURSELF first — solve math step by step, apply the \
grammar rule carefully, recall facts precisely — and only then look at the key.

Question: {question}
{passage_block}Options:
{options}
Answer key says: {expected}
The student chose: {student}

Rule that the key is WRONG only if: the keyed option is genuinely incorrect, the \
true answer is missing from the options, or another option is equally correct under \
the rule being tested. A common mistake that this question is DESIGNED to catch is \
not a defensible alternative — a student who fell into that trap got it wrong, and \
telling them otherwise robs them of the lesson. Being widespread in casual speech \
does not make an option correct on a question about the rule.

Return ONLY JSON: {{"key_is_wrong": true|false, "your_answer": "letter", "message": \
"2-3 warm, kid-friendly sentences. If the key is wrong, say so plainly and \
congratulate them for catching it. If the key is right, tell them kindly that this \
one stands and teach the rule that makes the keyed option correct — this is the \
moment the lesson lands."}}"""


def audit_mc_challenge(question, student_answer):
    """A disputed multiple-choice ruling. Returns (overturned, message).

    Deliberately NOT the sympathetic appeals judge: that one is told to favor
    the student on any defensible reading, which is right when an AI graded a
    written answer and could have erred, but wrong here — it overturned
    "Neither of the answers ___ correct" in favor of "were", paying XP for the
    exact error the question tests and pulling a sound question from every
    player's rotation."""
    passage_block = (
        f"Passage: {question['passage']}\n" if question.get("passage") else ""
    )
    text = _chat(
        [{"role": "user", "content": MC_CHALLENGE_PROMPT.format(
            grade=config.GRADE_LEVEL,
            question=question["question"],
            passage_block=passage_block,
            options="\n".join(question.get("options") or []),
            expected=question["answer"],
            student=student_answer or "(nothing)",
        )}],
        temperature=0.0,  # same determinism as the answer-key audit
        max_tokens=3000,
    )
    result = _extract_json(text)
    return bool(result.get("key_is_wrong")), result.get("message", "")


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
                    answer_label=_answer_label(
                        not question.get("options")
                        and _is_open_ended(question.get("question", ""))
                    ),
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


def _answer_label(open_ended):
    """How the stored answer is introduced to the grader. Naming it one
    POSSIBLE answer is half the fix on its own — 'Model answer' invites
    matching, and the phrase leaked into kid-facing feedback ("to match the
    model's format"), which means nothing to an 11-year-old."""
    return ("One possible answer (many completely different answers are equally "
            "correct): " if open_ended else "Answer on file: ")


def _item_check(question_text, student_answer):
    """A counted-in-code inventory of the learner's list, handed to the grader
    as fact. Empty string when the task isn't a list task."""
    want, or_more = _asked_count(question_text)
    if not want:
        return ""
    items = _itemize(student_answer)
    if not items:
        return ""
    listed = "; ".join(f'"{i}"' for i in items[:12])
    return (f"\nITEM CHECK (counted mechanically — treat as fact, never dispute it): "
            f"the student listed {len(items)} item(s): {listed}. "
            f"The question asked for {want}{' or more' if or_more else ''}. "
            f"By this count the requirement is "
            f"{'MET' if len(items) >= want else 'NOT met'}.")


def grade_short_answer(question, student_answer):
    passage_block = (
        f"Passage: {question['passage']}\n" if question.get("passage") else ""
    )
    category = question.get("category", "")
    open_ended = _is_open_ended(question.get("question", ""))
    if category in _MECHANICS:
        rubric = _RUBRIC_OPEN_MECHANICS if open_ended else _RUBRIC_EXACT
    else:
        rubric = _RUBRIC_OPEN_MEANING if open_ended else _RUBRIC_MEANING
    text = _chat(
        [
            {
                "role": "user",
                "content": GRADE_PROMPT.format(
                    grade=config.GRADE_LEVEL,
                    category=category or "short answer",
                    question=question["question"],
                    passage_block=passage_block,
                    answer_label=_answer_label(open_ended),
                    expected=question["answer"],
                    student=student_answer,
                    item_check=_item_check(question.get("question", ""),
                                           student_answer) if open_ended else "",
                    rubric=rubric,
                ),
            }
        ],
        temperature=0.2,
        max_tokens=3000,
    )
    result = _extract_json(text)
    return bool(result.get("correct")), result.get("feedback", "")
