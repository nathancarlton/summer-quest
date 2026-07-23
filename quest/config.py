"""Configuration: loads .env, defines paths and constants."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

PROFILE_PATH = DATA_DIR / "profile.json"
HISTORY_PATH = DATA_DIR / "history.jsonl"
SYNC_QUEUE_PATH = DATA_DIR / "sync_queue.jsonl"

# --- MiniMax (OpenAI-compatible) ---
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
MINIMAX_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimax.io/v1")
MINIMAX_MODEL = os.getenv("MINIMAX_MODEL", "MiniMax-M3")

# --- Sync (stub for future Render backend) ---
SYNC_URL = os.getenv("SYNC_URL", "")
SYNC_TOKEN = os.getenv("SYNC_TOKEN", "")

# --- Session shape ---
QUESTIONS_PER_SESSION = int(os.getenv("QUESTIONS_PER_SESSION", "10"))

# Family voice chat unlocks at this level — a progress reward. Calls are
# free-form, family-roster-only, and peer-to-peer (no audio on the server).
VOICE_CHAT_MIN_LEVEL = int(os.getenv("VOICE_CHAT_MIN_LEVEL", "5"))
LA_RATIO = float(os.getenv("LA_RATIO", "0.7"))  # 70% language arts by default
# Per-question time limit (web): 10 × 90s ≈ a 15-minute daily session.
QUESTION_SECONDS = int(os.getenv("QUESTION_SECONDS", "120"))

GRADE_LEVEL = "6th grade (incoming), Minnesota MCA-aligned"

XP_PER_CORRECT = 10
XP_BOSS_MULTIPLIER = 2
XP_STREAK_BONUS = 5  # per day of active streak, awarded on session completion

LEVELS = [
    (0, "Word Sprout"),
    (100, "Sentence Scout"),
    (250, "Paragraph Pathfinder"),
    (450, "Grammar Guardian"),
    (700, "Vocab Voyager"),
    (1000, "Essay Explorer"),
    (1400, "Metaphor Master"),
    (1900, "Comprehension Champion"),
    (2500, "Literary Legend"),
    (3500, "MCA Mythic"),
]

CATEGORIES = {
    "vocabulary": "la",
    "grammar": "la",
    "reading": "la",
    "figurative_language": "la",
    "writing_mechanics": "la",
    "math_challenge": "math",
}

# Subtopic balancing: for any category listed here, question generation and
# per-learner tracking rotate evenly through these subtopics. Left to itself
# the model collapses onto the most prototypical concepts (nearly every
# figurative_language question came out simile/metaphor); an explicit
# least-practiced-first rotation keeps coverage even. Add a list for any
# category that needs the same treatment.
SUBTOPICS = {
    "figurative_language": [
        "simile", "metaphor", "personification", "hyperbole",
        "idiom", "onomatopoeia", "alliteration",
    ],
    "math_challenge": [
        "ratios", "rates", "percentages", "mean", "median", "mode",
        "range", "percentile", "pre-algebra", "multi-step logic",
    ],
}

# --- Personalization ---
# One theme is chosen per session so questions feel like a single little world
# (the way an AI-generated "lighthouse" thread felt during playtesting).
THEMES = [
    "a mysterious lighthouse", "a space station orbiting Mars",
    "a hidden jungle temple", "a championship soccer match",
    "a video game come to life", "a detective mystery downtown",
    "a deep-sea submarine voyage", "a wildlife photographer's safari",
    "a summer carnival at night", "a robot's first day of school",
    "a time-traveler's train station", "a wildlife rescue center",
    "an inventor's cluttered workshop", "a night market in a faraway city",
    "an arctic research base", "a movie set where everything goes wrong",
    "a giant treehouse city", "a baking championship finale",
    "a secret library beneath the school", "a storm-chasing road trip",
]

# Favorite food -> the small thing you count in a word problem. Falls back to
# "pieces" for anything not listed, so any answer the kid gives still works.
FOOD_UNITS = {
    "pizza": "pepperoni slices", "cookies": "chocolate chips",
    "tacos": "taco shells", "sushi": "sushi rolls", "burgers": "pickle slices",
    "ice cream": "sprinkles", "pancakes": "blueberries", "donuts": "sprinkles",
    "popcorn": "kernels", "spaghetti": "meatballs", "nachos": "cheese chips",
}
DEFAULT_FOOD_UNIT = "pieces"
