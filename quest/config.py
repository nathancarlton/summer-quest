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
MINIMAX_MODEL = os.getenv("MINIMAX_MODEL", "MiniMax-M2.5")

# --- Sync (stub for future Render backend) ---
SYNC_URL = os.getenv("SYNC_URL", "")
SYNC_TOKEN = os.getenv("SYNC_TOKEN", "")

# --- Session shape ---
QUESTIONS_PER_SESSION = int(os.getenv("QUESTIONS_PER_SESSION", "10"))
LA_RATIO = float(os.getenv("LA_RATIO", "0.7"))  # 70% language arts by default

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
