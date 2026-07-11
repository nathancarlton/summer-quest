# 🗺️ Summer Quest

A daily 15–30 minute CLI learning game for incoming 6th graders, aligned to Minnesota MCA skills. Weighted toward **language arts** (70%) with hard **math challenges** (30%). Questions are generated fresh every day by **MiniMax**, with an offline question pack as fallback.

## Features

- **AI-generated daily quests** — vocabulary, grammar, reading comprehension (with passages), figurative language, writing mechanics, and multi-step math word problems
- **Adaptive** — tracks per-category accuracy and tells the AI to emphasize weak areas
- **AI-graded written answers** — short-answer questions get generous, encouraging feedback
- **Gamification** — XP, 10 named levels, daily streaks with bonus XP, 9 unlockable badges, and a double-XP **boss battle** at the end of each session
- **Progress tracking** — local profile + append-only session history, plus a sync stub ready to point at a future API backend
- **Offline-safe** — no API key or no internet? Falls back to a built-in question bank; sync events queue and flush later

## Setup (Mac & Windows)

Requires Python 3.9+.

```bash
git clone https://github.com/nathancarlton/summer-quest
cd summer-quest
python3 -m venv .venv

# Mac/Linux:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
copy .env.example .env    # Windows
cp .env.example .env      # Mac/Linux
```

Edit `.env` and paste your MiniMax API key. Then run:

```bash
python3 -m quest
```

First run asks for the learner's name and creates their profile (one profile per machine — one per twin).

## Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `MINIMAX_API_KEY` | — | Your MiniMax key. Blank = offline mode. |
| `MINIMAX_BASE_URL` | `https://api.minimax.io/v1` | OpenAI-compatible endpoint |
| `MINIMAX_MODEL` | `MiniMax-M2.7` | Any MiniMax chat model |
| `SYNC_URL` | blank | Future backend base URL. Blank = sync disabled. |
| `SYNC_TOKEN` | blank | Bearer token for the backend |
| `QUESTIONS_PER_SESSION` | `10` | Session length |
| `LA_RATIO` | `0.7` | Language arts share of each session |

## Project layout

```
quest/
  __main__.py   # entry point / menu
  config.py     # env, paths, XP/level constants, themes, food→unit map
  ai.py         # MiniMax client: batched question gen + short-answer grading
  bank.py       # offline fallback pack + personalized templates
  pool.py       # pre-generated question pool + background refill
  profile.py    # XP, streaks, badges, category stats, prefs, offline mastery
  session.py    # the daily quest loop
  sync.py       # sync stub (POST /api/v1/progress) + offline queue
  ui.py         # rich-based terminal UI
data/           # gitignored: profile.json, history.jsonl, pool.jsonl, sync queue
```

## How questions load (instant, then fresh)

The reasoning model takes ~1 min to write a full themed quest, so it never sits
in the critical path:

1. **Serve now:** each quest starts instantly — from a pre-generated themed
   session in `data/pool.jsonl`, or (first run) from the personalized offline
   bank in `bank.py`.
2. **Brew next:** a background thread generates the *next* session's themed,
   personalized questions into the pool while the kid plays. By the second
   session, questions are AI-fresh **and** instant.
3. **Judgement only:** MiniMax is used live only to grade written short answers
   (shown with an "Evaluating your answer…" spinner).

Questions answered correctly from the offline bank are retired; missed ones
return in a **later** session until mastered (spaced repetition). A per-session
**theme** (a lighthouse, a Mars station…) and the kid's **favorites** (favorite
animal, favorite food → counting pepperoni/chocolate chips) thread through both
AI and offline questions.

## Data & progress

- `data/profile.json` — the learner's full state (XP, streak, badges, per-category accuracy, prefs, offline mastery)
- `data/history.jsonl` — one line per completed session
- `data/pool.jsonl` — queued pre-generated sessions (safe to delete; it refills)
- Parent check-in: option **2 (My stats)** in the app shows the report card, or just read the JSON

## Path to the React + Render version

The CLI was built so the backend swap is mechanical:

1. **API backend (Render):** implement `POST /api/v1/progress` per the contract documented in `quest/sync.py` — the CLI already sends full profile + session summaries and handles auth via `SYNC_TOKEN`. Add `GET /api/v1/profile/:id` for cross-device state.
2. **Question service:** lift `ai.py` into the backend verbatim (it's pure Python + requests) so the MiniMax key lives server-side, then expose `POST /api/v1/quest` returning the same question JSON schema.
3. **React frontend:** `session.py` is the game loop spec; `ui.py` maps 1:1 to components (HUD, QuestionCard, BossBanner, SummaryTable, ReportCard). All state is already JSON.

## Notes

- Never commit `.env` (already gitignored). Each twin's machine gets its own `.env` and its own `data/` profile.
- The offline pack in `bank.py` is small by design — add to it if you expect long stretches without internet.
