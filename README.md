# 🗺️ Summer Quest

A daily 15–30 minute learning game for incoming 6th graders, aligned to Minnesota MCA skills. Weighted toward **language arts** (70%) with hard **math challenges** (30%). Questions are generated fresh every day by **MiniMax**, with an offline question pack as fallback.

Comes in two forms that share the same game engine:

- **CLI** (`quest/`) — the original terminal game, one profile per machine
- **Web** — a React frontend (`frontend/`, deploy to **Vercel**) talking to a FastAPI backend (`backend/`, deploy to **Render**, with **Supabase** Postgres for storage), with multiple player profiles per device and the MiniMax key kept server-side

## Features

- **AI-generated daily quests** — vocabulary, grammar, reading comprehension (with passages), figurative language, writing mechanics, and multi-step math word problems
- **Adaptive** — tracks per-category accuracy and tells the AI to emphasize weak areas; a challenge level (1–5) rises when a kid scores 90%+ and eases when they score 50% or below, keeping sessions in the productive ~7–8/10 zone
- **Personalized, privately** — favorites (color, dream destination, instrument, sport, song, weather, animal, food) get woven into questions; each badge earned unlocks a bonus prompt to add or refresh one. The catalog is deliberately impersonal — things, places, weather; never names of people — so profiles don't collect identifying details
- **AI-graded written answers** — short-answer questions get generous, encouraging feedback
- **Gamification** — XP, 10 named levels, daily streaks with bonus XP, unlockable badges, and a double-XP **boss battle** at the end of each session (with a hype-building intro that recaps the run before the final showdown)
- **Expeditions** 🧭 — trivia side-quests across six worlds (Science Lab, Wild World, Body & Food, Money Matters, We the People, Map Masters) earning **Sparks ⚡** and collectible **stickers** — a separate economy from XP. AI-generated after the daily-quest pool fills, with a curated offline trivia bank so they always start instantly; safety topics are framed as safety knowledge, never instructions
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
| `SYNC_URL` | blank | Backend base URL for CLI sync. Blank = sync disabled. |
| `SYNC_TOKEN` | blank | Bearer token for the backend |
| `QUESTIONS_PER_SESSION` | `10` | Session length |
| `LA_RATIO` | `0.7` | Language arts share of each session |

## Project layout

```
quest/            # shared game engine + the CLI
  __main__.py     # CLI entry point / menu
  config.py       # env, paths, XP/level constants, themes, food→unit map
  ai.py           # MiniMax client: batched question gen + short-answer grading
  bank.py         # offline fallback pack + personalized templates
  pool.py         # CLI's pre-generated question pool + background refill
  profile.py      # XP, streaks, badges, category stats, prefs, offline mastery
  session.py      # the CLI's daily quest loop
  sync.py         # CLI→backend sync (POST /api/v1/progress) + offline queue
  ui.py           # rich-based terminal UI
backend/app/      # FastAPI backend (imports quest/ directly — no duplication)
  main.py         # routes + CORS
  engine.py       # the quest loop as HTTP: start → answer × n → complete
  storage.py      # SQLite locally, Postgres via DATABASE_URL in production
frontend/         # React (Vite) app for Vercel
  src/screens/    # PickPlayer, Onboarding, Home (HUD), Quest, Summary, Stats
render.yaml       # Render service definition (build + start commands, env vars)
Procfile          # same boot command for Heroku-style hosts (Koyeb/Zeabur)
data/             # gitignored: CLI profile + history, local SQLite db
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

## The web version

### Run it locally

```bash
# Terminal 1 — backend (uses your root .env for the MiniMax key)
pip install -r requirements.txt
uvicorn backend.app.main:app --reload          # http://localhost:8000

# Terminal 2 — frontend
cd frontend
npm install
npm run dev                                     # http://localhost:5173
```

The frontend reads `VITE_API_URL` (defaults to `http://localhost:8000`).

### API

| Endpoint | Purpose |
|---|---|
| `GET /` | health check |
| `GET /api/v1/players` | roster for the "who's playing?" picker |
| `POST /api/v1/players` | create a profile (`{name, prefs}`) |
| `GET /api/v1/players/{id}` | profile + computed level/badges |
| `POST /api/v1/players/{id}/quest` | start today's quest (`{local_date}`) — returns questions **without answers** |
| `POST /api/v1/quests/{id}/answer` | grade the next answer server-side (MiniMax grades written ones) |
| `POST /api/v1/quests/{id}/complete` | streak bonus, badges, history |
| `POST /api/v1/progress` | the CLI's sync contract (Bearer `SYNC_TOKEN`) |

Answers never reach the browser: grading happens on the server, so a curious kid can't peek in DevTools. Question generation works exactly like the CLI — instant serve from a per-player pre-generated pool (or the offline bank on first play), while a background thread brews the next themed session.

### Set up the database — Supabase

Free web hosts have ephemeral disks (wiped on every deploy), so the kids' XP
must live in Postgres. Without `DATABASE_URL` the backend falls back to SQLite —
fine for local dev only.

1. Create a project at [supabase.com](https://supabase.com) (free tier).
2. Project → **Connect** → copy the **Session pooler** URI (not "Direct
   connection" — direct is IPv6-only on the free plan and Render can't reach it):
   `postgresql://postgres.xxxx:[password]@aws-0-us-east-1.pooler.supabase.com:5432/postgres`
3. Replace `[password]` with your database password. This is your `DATABASE_URL`.

Note: free Supabase projects pause after ~1 week of inactivity. Daily play keeps
it awake; after a long vacation, un-pause it in the Supabase dashboard (Restore).

### Deploy the backend — Render

1. [render.com](https://render.com) → New → **Web Service** → connect this repo,
   branch `main`. The root `render.yaml` supplies the build and start commands
   (or enter them manually: build `pip install -r requirements.txt`, start
   `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`). Pick the free
   instance type.
2. Set environment variables on the service:
   - `MINIMAX_API_KEY` — so generation/grading runs server-side
   - `DATABASE_URL` — the Supabase pooler URI from above
   - `CORS_ORIGINS` — set to your Vercel URL once you have it, e.g. `https://summer-quest.vercel.app` (unset = allow all, handy while testing)
   - `SYNC_TOKEN` — optional, only if the CLIs will sync to this backend
3. Note the public URL, e.g. `https://summer-quest-api.onrender.com` — check `GET /` returns `{"status": "healthy"}`.

(Don't use Render's own free Postgres for this — it expires and is deleted after
30 days. The `Procfile` also still works on Heroku-style hosts like Zeabur if
you ever switch.)

### Deploy the frontend — Vercel

1. Vercel → Add New Project → import this repo.
2. Set **Root Directory** to `frontend` (Vite is auto-detected; build command `npm run build`, output `dist`).
3. Add env var `VITE_API_URL` = your backend URL from above (no trailing slash).
4. Deploy, then go back to Render and set `CORS_ORIGINS` to the Vercel URL.

Every `git push` now rebuilds both halves automatically.

### Import existing CLI progress

If a kid has been playing the CLI version, move their profile online once
(from the repo root on their machine, venv active):

```bash
python3 scripts/import_cli_progress.py https://your-backend-url
```

XP, streak, badges, favorites, mastered questions, and session history all
carry over; their name then appears in the web app's player picker. The script
refuses to run twice for the same player unless you pass `--force`.

### The AI status dot

A small dot on the home screen (and during quests) shows whether MiniMax is
working behind the scenes: green = last AI call succeeded, red = last call
failed (the game silently falls back to the offline pack), gray = no key set,
amber = no AI call yet since the server booted. Clicking it fires a real test
call. The same info is at `GET /api/v1/ai/status?probe=true` on the backend.

### Point the CLI at the backend (optional)

Set in each machine's `.env`: `SYNC_URL=https://your-backend-url` and a matching `SYNC_TOKEN` — completed CLI sessions then appear in the backend's history via the contract in `quest/sync.py`.

### Free-tier notes

- Free backends **sleep** when idle (Render spins down after ~15 min); the first request of the day takes ~10–30s to wake. The frontend shows its "summoning" spinner during this — FastAPI itself boots in milliseconds, so the platform wake-up dominates.
- The background question-brewing thread only runs while the instance is awake (i.e., while someone is playing). If a freshly woken instance has an empty pool, the quest starts instantly from the offline bank and the AI session is ready next time — same graceful degradation as the CLI.

## Notes

- Never commit `.env` (already gitignored). Each twin's machine gets its own `.env` and its own `data/` profile.
- The offline pack in `bank.py` is small by design — add to it if you expect long stretches without internet.
