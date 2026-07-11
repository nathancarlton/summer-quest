"""MiniMax client (OpenAI-compatible chat completions).

Generates question sets and grades open-ended answers. All AI calls
degrade gracefully: on any failure, callers fall back to the offline bank
or local grading.
"""
import json
import re

import requests

from . import config

TIMEOUT = 45


class AIUnavailable(Exception):
    pass


def _chat(messages, temperature=0.8, max_tokens=2000):
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
    # Strip <think>...</think> blocks some MiniMax models emit
    return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()


def _extract_json(text):
    text = re.sub(r"```(?:json)?|```", "", text).strip()
    start = min((i for i in (text.find("["), text.find("{")) if i != -1), default=-1)
    if start == -1:
        raise ValueError("No JSON found in AI response")
    return json.loads(text[start:])


GEN_SYSTEM = """You create engaging practice questions for a student entering \
{grade}. Tone: fun, adventurous, encouraging — like a quest game. \
Return ONLY a JSON array, no prose, no markdown fences."""

GEN_PROMPT = """Create {n} questions with this category mix: {mix}.

Student context:
- Strong at math: math_challenge questions should be genuinely hard word \
problems (ratios, rates, pre-algebra, multi-step logic).
- Needs growth in language arts: target Minnesota MCA reading/language skills. \
Weakest categories lately (emphasize these skills within their categories): {weak}.

Question types: "mc" (4 options) or "short" (one-sentence written answer). \
Use "short" for at least 2 language arts questions. For "reading" questions, \
include a 3-5 sentence original passage in the "passage" field.

Each JSON object:
{{"category": "...", "type": "mc"|"short", "question": "...", \
"passage": "..." or null, "options": ["A...","B...","C...","D..."] or null, \
"answer": "correct option letter or model short answer", \
"explanation": "kid-friendly why"}}

Make the LAST question a tough "boss battle" reading or figurative_language \
question. Vary themes kids like: space, animals, sports, video games, mysteries."""


def generate_questions(n, mix, weak_categories):
    weak = ", ".join(weak_categories) if weak_categories else "none identified yet"
    text = _chat(
        [
            {"role": "system", "content": GEN_SYSTEM.format(grade=config.GRADE_LEVEL)},
            {"role": "user", "content": GEN_PROMPT.format(n=n, mix=mix, weak=weak)},
        ]
    )
    questions = _extract_json(text)
    if not isinstance(questions, list) or not questions:
        raise ValueError("AI returned unexpected shape")
    return questions


GRADE_PROMPT = """A {grade} student answered a practice question.

Question: {question}
{passage_block}Expected answer (model answer): {expected}
Student's answer: {student}

Grade generously — accept reasonable paraphrases and partial understanding. \
Return ONLY JSON: {{"correct": true|false, "feedback": "1-2 encouraging, \
specific sentences. If wrong, teach the idea simply."}}"""


def grade_short_answer(question, student_answer):
    passage_block = (
        f"Passage: {question['passage']}\n" if question.get("passage") else ""
    )
    text = _chat(
        [
            {
                "role": "user",
                "content": GRADE_PROMPT.format(
                    grade=config.GRADE_LEVEL,
                    question=question["question"],
                    passage_block=passage_block,
                    expected=question["answer"],
                    student=student_answer,
                ),
            }
        ],
        temperature=0.2,
        max_tokens=400,
    )
    result = _extract_json(text)
    return bool(result.get("correct")), result.get("feedback", "")
