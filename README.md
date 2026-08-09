# 🗺️ Summer Quest

A daily 15–30 minute learning game for incoming 6th graders, aligned to Minnesota MCA skills. Weighted toward **language arts** (70%) with hard **math challenges** (30%). Questions are generated fresh every day by **MiniMax**, with an offline question pack as fallback.

Comes in two forms that share the same game engine:

- **CLI** (`quest/`) — the original terminal game, one profile per machine
- **Web** — a React frontend (`frontend/`, deploy to **Vercel**) talking to a FastAPI backend (`backend/`, deploy to **Render**, with **Supabase** Postgres for storage), with multiple player profiles per device and the MiniMax key kept server-side

## Features

- **AI-generated daily quests** — vocabulary, grammar, reading comprehension (with passages), figurative language, writing mechanics, and multi-step math word problems
- **Adaptive** — tracks per-category accuracy and tells the AI to emphasize weak areas; a challenge level (1–5) rises when a kid scores 90%+ and eases when they score 50% or below, keeping sessions in the productive ~7–8/10 zone
- **Subtopic balancing** — categories in `config.SUBTOPICS` rotate evenly through their concepts *per learner*: figurative language cycles all seven devices (simile, metaphor, personification, hyperbole, idiom, onomatopoeia, alliteration) instead of collapsing onto simile/metaphor, and math cycles ratios, rates, percentages, mean, median, mode, range, percentile, pre-algebra, and multi-step logic. The profile tracks per-subtopic exposure; generation prompts and bank sampling both lead with what that learner has practiced least
- **Personalized, privately** — favorites (color, dream destination, instrument, sport, song, weather, animal, food) get woven into questions; each badge earned unlocks a bonus prompt to add or refresh one. The catalog is deliberately impersonal — things, places, weather; never names of people — so profiles don't collect identifying details
- **AI-graded written answers** — short-answer questions get generous, encouraging feedback
- **Challenges & reports** — a learner who disputes a ruling can hit "⚖️ Challenge it" for an independent AI re-evaluation, or report any question to the game developers (see [Question quality](#question-quality-verification-before-a-learner-ever-sees-it) below)
- **Gamification** — XP, 10 named levels, daily streaks with bonus XP, unlockable badges, and a double-XP **boss battle** at the end of each session (with a hype-building intro that recaps the run before the final showdown)
- **Timed & rage-quit-proof (web)** — 120 seconds per question (`QUESTION_SECONDS`; 10 × 120s ≈ a 20-minute session ceiling) with a countdown and auto-timeout; sessions live server-side, so closing the browser mid-game changes nothing — the home screen offers exactly one button, "Finish your quest!", resuming at the first unanswered question with all previous answers locked in. No restart path exists, and expeditions can't be used as an escape hatch either
- **Expeditions** 🧭 — trivia side-quests across six worlds (Science Lab, Wild World, Body & Food, Money Matters, We the People, Map Masters) earning **Sparks ⚡** and collectible **stickers** — a separate economy from XP. AI-generated after the daily-quest pool fills, with a curated offline trivia bank so they always start instantly; safety topics are framed as safety knowledge, never instructions
- **Reading Room** 📖 — eight public-domain classics (Treasure Island, The Call of the Wild, The Wonderful Wizard of Oz, Alice in Wonderland, Tarzan of the Apes, The Adventures of Sherlock Holmes, and both Verne voyages) served chapter by chapter with per-kid progress. Opening a chapter starts brewing a 3-question AI comprehension quiz about *that exact chapter* — finish reading, take the quiz, earn regular XP (which also feeds the reading-category stats). Texts fetch once from Project Gutenberg and cache in the database; one quiz per chapter is shared family-wide. Reading pays nothing by itself — the quiz is the XP gate, so clicking "next" through a book earns zero
- **Question quality pipeline** — generated questions pass a confused-explanation filter and an **adversarial answer-key audit** (an independent AI pass re-solves every multiple-choice question) before earning a `verified` flag; the serve gate refuses to hand a learner anything unverified. If a bad one still slips through, the challenge button catches it and auto-reports it
- **Family leaderboard** — everyone ranked by XP with levels, streaks, badges, and Sparks
- **Post-quest standings** — every results screen ends with a compare-and-contrast moment: your rank, the real XP gap to the player just ahead (and behind), and who leads the board
- **Combine-profiles offer** — a parent can queue a `merge_offer` on a player record (`{source_pid, bonus_xp}`); after their next quest — right below the standings — the kid sees an honest pitch to fold an old profile into this one (its real XP, a reunion bonus, the level they'd land on). Accepting merges XP, stats, badges, mastery, stickers, and history, then retires the old profile
- **Family Phone** 📞 — a progress reward at Level 5: free-form voice calls between family players, about anything at all. WebRTC peer-to-peer audio (never touches the server); the backend only runs a WebSocket switchboard relaying ring/accept/decline between logged-in, unlocked players
- **Looks** — four color themes (Sunset, Ocean, Forest, Midnight) and three fonts (Fredoka, Nunito, Inter), each remembered per device
- **Progress tracking** — full profile + append-only session history, synced between the CLI and the web backend
- **Offline-safe** — no API key or no internet? Falls back to a built-in bank of 165 curated questions (plus 36 expedition trivia); sync events queue and flush later

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
| `MINIMAX_MODEL` | `MiniMax-M3` | Any MiniMax chat model |
| `SYNC_URL` | blank | Backend base URL for CLI sync. Blank = sync disabled. |
| `SYNC_TOKEN` | blank | Bearer token for the backend (also protects `GET /api/v1/reports`) |
| `QUESTIONS_PER_SESSION` | `10` | Session length |
| `LA_RATIO` | `0.7` | Language arts share of each session |
| `QUESTION_SECONDS` | `120` | Per-question time limit in the web app |
| `VOICE_CHAT_MIN_LEVEL` | `5` | Level that unlocks the Family Phone |
| `DATABASE_URL` | blank | Backend only: Postgres for durable storage (else local SQLite) |
| `CORS_ORIGINS` | blank | Backend only: comma-separated allowed browser origins (blank = all) |

## Project layout

```
quest/            # shared game engine + the CLI
  __main__.py     # CLI entry point / menu
  config.py       # env, paths, XP/level constants, themes, food→unit map
  ai.py           # MiniMax client: generation, grading, appeals judge, key audit
  bank.py         # offline question pack (165) + personalized templates
  expeditions.py  # trivia topic catalog + curated offline expedition bank
  pool.py         # CLI's pre-generated question pool + background refill
  profile.py      # XP, streaks, badges, difficulty, prefs, offline mastery
  session.py      # the CLI's daily quest loop
  sync.py         # CLI→backend sync (POST /api/v1/progress) + offline queue
  ui.py           # rich-based terminal UI
backend/app/      # FastAPI backend (imports quest/ directly — no duplication)
  main.py         # routes + CORS
  engine.py       # quests, expeditions, resume, challenges, pools + serve gate,
                  # standings, profile merges
  voice.py        # Family Phone signaling (WebSocket switchboard for WebRTC)
  storage.py      # SQLite locally, Postgres via DATABASE_URL in production
frontend/         # React (Vite) app for Vercel
  src/screens/    # PickPlayer, Onboarding, Home, Quest, Summary, Stats,
                  # Leaderboard, Topics (expeditions), VoiceChat (Family Phone)
scripts/          # one-shot deploy helpers + CLI-progress importer
.github/workflows/ # push-to-deploy: calls the Render deploy hook
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
| `GET /` | health check (`commit` field shows the deployed git SHA) |
| `GET /api/v1/players` | roster for the "who's playing?" picker (names + has_secret only) |
| `POST /api/v1/players` | create a profile (`{name, prefs, secret, hint}`) → auth token |
| `POST /api/v1/players/{id}/login` | `{secret}` → auth token (5 tries/min) |
| `GET /api/v1/players/{id}/hint` | the player's password hint |
| `POST /api/v1/players/{id}/secret` | first-time secret creation (CLI imports); changing requires login |
| `POST /api/v1/players/{id}/lockout` | "I forgot my password" → notifies the game developers |
| `POST /api/v1/players/{id}/logout` | sign out: revokes this device's token, closes the session in the parent view |
| `POST /api/v1/players/{id}/name` | change your display name (owner-only; names stay unique in the family) |
| `POST /api/v1/players/{id}/secret/reset` | parent reset (Bearer `SYNC_TOKEN` when set) |
| `GET /api/v1/players/{id}` | profile + computed level/badges/active-session state |
| `GET /api/v1/players/{id}/active` | is there an unfinished session? |
| `GET /api/v1/players/{id}/history` | completed-session summaries |
| `POST /api/v1/players/{id}/prefs` | add/refresh one favorite (server whitelists the catalog) |
| `POST /api/v1/players/{id}/quest` | start today's quest (`{local_date}`) — returns questions **without answers**; returns the in-flight session instead if one is unfinished |
| `POST /api/v1/players/{id}/expedition` | start a trivia expedition (`{topic}`, omit for random) |
| `GET /api/v1/expeditions` | the six expedition topics |
| `POST /api/v1/quests/{id}/answer` | grade the next answer server-side (MiniMax grades written ones; server also enforces the per-question time limit) |
| `POST /api/v1/quests/{id}/challenge` | dispute a wrong ruling — an independent AI appeals pass re-evaluates |
| `POST /api/v1/quests/{id}/report` | flag a question for the game developers |
| `POST /api/v1/quests/{id}/complete` | streak bonus, badges, difficulty adjustment, history — plus family standings and any pending combine-profiles offer |
| `POST /api/v1/players/{id}/merge` | accept a pending combine-profiles offer (owner-only) |
| `WS /api/v1/voice/ws?token=…` | Family Phone signaling: roster presence + call/accept/decline/SDP relay (players at `VOICE_CHAT_MIN_LEVEL`+) |
| `GET /api/v1/leaderboard` | all players ranked by XP |
| `GET /api/v1/ai/status` | is MiniMax working? `?probe=true` fires a live test call |
| `GET /api/v1/reports` / `DELETE /api/v1/reports` | flagged questions + auto-filed challenge wins (requires `SYNC_TOKEN` when set) |
| `GET /api/v1/activity?days=14` | parent view: sign-ins, what happened, sign-outs (requires `SYNC_TOKEN` when set) |
| `POST /api/v1/progress` | the CLI's sync contract (Bearer `SYNC_TOKEN`) |

Answers never reach the browser: grading happens on the server, so a curious kid can't peek in DevTools. Question generation works exactly like the CLI — instant serve from a per-player pre-generated pool (or the offline bank on first play), while a background thread brews the next themed session and audits anything not yet verified.

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
   - `CORS_ORIGINS` — set to your Vercel URL once you have it, e.g. `https://summer-quest.vercel.app` (unset = allow all — fine while testing, but lock this down for a public deploy; see Security below)
   - `SYNC_TOKEN` — recommended: protects `GET /api/v1/reports` (question text + kids' answers) and the CLI sync endpoint
3. Note the public URL, e.g. `https://summer-quest-api.onrender.com` — check `GET /` returns `{"status": "healthy", "commit": "..."}`.

(Don't use Render's own free Postgres for this — it expires and is deleted after
30 days. The `Procfile` also still works on Heroku-style hosts like Zeabur if
you ever switch.)

**Keeping push-to-deploy working:** services created via Render's dashboard get
GitHub push webhooks automatically, but one created via the API/CLI (as
`scripts/deploy_render.sh` does) does not — its "Auto-Deploy: On Commit" setting
has nothing to fire it. `.github/workflows/deploy-backend.yml` covers this by
calling the service's Deploy Hook on every push that touches backend code.
One-time setup: Render dashboard → the service → Settings → Deploy → copy the
**Deploy Hook** URL → GitHub repo → Settings → Secrets and variables → Actions →
add a secret named `RENDER_DEPLOY_HOOK` with that URL. Without this secret,
backend deploys must be triggered manually (`bash scripts/deploy_render.sh` or
Render's "Manual Deploy" button) — worth checking the `commit` field at `GET /`
against `git log` if something you pushed doesn't seem to be live.

### Deploy the frontend — Vercel

1. Vercel → Add New Project → import this repo.
2. Set **Root Directory** to `frontend` (Vite is auto-detected; build command `npm run build`, output `dist`).
3. Add env var `VITE_API_URL` = your backend URL from above (no trailing slash). This value is **public** — it ends up in the built JS bundle, same as any frontend config.
4. Deploy, then go back to Render and set `CORS_ORIGINS` to the Vercel URL.

Every `git push` to `main` now redeploys both halves automatically (frontend via
Vercel's native GitHub integration, backend via the Actions workflow above).

### Deploy scripts (optional shortcut)

`scripts/deploy_render.sh` and `scripts/deploy_vercel.sh` drive the same setup
from the command line via each platform's API — handy for scripting the whole
stack in one go instead of clicking through both dashboards. They take API
tokens as env vars (`RENDER_KEY`, `VERCEL_TOKEN`) and are idempotent — re-running
updates the existing service instead of duplicating it. Treat those tokens as
full account credentials: create them, run the script, then delete the token
from the platform's dashboard.

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

### Question quality: verification before a learner ever sees it

Generated questions go through several layers before they're servable:

1. **Confused-explanation filter** — an explanation containing self-doubt
   tells ("wait, that's not an option", "let me check again") means the model
   caught its own mistake; that question is dropped rather than shown.
2. **Adversarial answer-key audit** — a second, independent AI pass re-solves
   every multiple-choice question from scratch and checks the official
   answer; questions that fail are dropped.
3. **Serve gate** — every pooled session carries a `verified` flag, earned by
   passing steps 1–2. The serve path refuses anything unverified; a
   background sweep audits and flags older pool entries the next time the
   pool is touched, falling back to the hand-curated offline bank meanwhile.

**Grading open-ended writing tasks.** When a task asks the learner to supply
their own content ("write three kinds of space objects, separating each with a
comma"), the stored answer is only one of countless correct responses.
Grading it as the target produced real nonsense — a learner who wrote "a star,
a planet, and a moon" was instructed to swap in the stored answer's nouns — so
those tasks are detected and graded differently: the answer is introduced as
one possible response, the rubric grades the mechanics being taught and
whether the content fits the request (never which items were chosen), and the
number of items the learner listed is **counted in Python** and handed to the
grader as fact, because counting is the part language models reliably flub.
Feedback may never reference the answer on file — the learner can't see it,
and "to match the model's format" means nothing to an 11-year-old.

If something still slips through, a learner can hit "⚖️ Challenge it" on a
wrong ruling — and which reviewer hears the appeal depends on what could
actually have gone wrong:

- **Written answers** go to a sympathetic appeals judge, told explicitly that
  the question or the original grader may be wrong. AI grading of prose is
  genuinely fallible, so the benefit of the doubt belongs with the learner.
- **Multiple choice** goes to the strict answer-key audit instead. MC answers
  are checked by letter match in code, so no grader can have erred — the only
  live question is whether the key is wrong. Sending these to the lenient
  judge produced the opposite failure from the grading bugs above: it
  overturned "Neither of the answers ___ correct" in favour of "were", paying
  XP for precisely the error the question was built to catch and pulling a
  sound question out of every player's rotation. The audit re-derives the
  answer at temperature 0 and is told that a mistake the question is *designed*
  to catch is not a defensible alternative, and that being common in speech
  doesn't make an option correct on a question about the rule. When it upholds
  the key, the learner gets the rule explained — the lesson is the point.

An overturn pays XP retroactively, corrects every stat the original ruling
touched, and pulls the question pending parent review. Any question can also
be reported directly via "📮 Report this question." Both land at
`GET /api/v1/reports`.

Two cross-player mechanisms tie it together (question ids are content-hashed,
so they work across everyone):

- **Global blocklist** — a reported or challenge-overturned question is
  instantly pulled from *every* player's rotation, not just the reporter's.
  The Parent Zone report card has a "♻️ restore" button if review shows the
  question was actually fine.
- **Shared bank** — every AI question that passes the audit joins a communal
  pool (capped per category) that tops up all players' sessions and
  expeditions, so one player's brewing benefits the whole family.

Generated multiple-choice sets are also screened for **length tells** — a
question whose correct option is dramatically longer than the others (the
"thorough-sounding answer is right" giveaway) is dropped, and the prompts
instruct the model to make wrong options the detailed-sounding ones as often
as right ones.

### The Parent Zone (admin)

The "🔧 Parent zone" link on the player-picker screen opens the admin view.
The admin key is the backend's `SYNC_TOKEN` — set it on the service
(`export SYNC_TOKEN=... && bash scripts/deploy_render.sh`, or via the Render
dashboard) and enter it once; it's remembered on that device. Two tabs:

**🕒 Activity** — who signed in when, what they did while they were on, and
when they left, grouped into visits under day headings and shown in your
local time. A roll-up across the window (7/14/30 days) gives last-seen,
visit count and minutes per player, plus a ⚠️ count of wrong-password
attempts. A visit with no sign-out reads "still open" — kids close the tab
far more often than they press "switch player", so its end time is the last
thing they actually did rather than a real goodbye. Events are recorded at
session boundaries (sign in/out, quest and expedition start/finish, chapter
opened, quiz taken, challenge, report, rename, password change) — never per
answer, which keeps the latency-critical answer path free of extra writes.

**📮 Reports** — flagged questions with the kid's answer and the feedback
they saw, overturned AI rulings, and locked-out password requests with a
one-click reset button (the kid creates a new secret at next login).

Until a `SYNC_TOKEN` is set, the Parent Zone is open — fine briefly, but set
one before sharing the app around.

### Point the CLI at the backend (optional)

Set in each machine's `.env`: `SYNC_URL=https://your-backend-url` and a matching `SYNC_TOKEN` — completed CLI sessions then appear in the backend's history via the contract in `quest/sync.py`.

### Free-tier notes

- Free backends **sleep** when idle (Render spins down after ~15 min); the first request of the day takes ~10–30s to wake. The frontend shows its "summoning" spinner during this — FastAPI itself boots in milliseconds, so the platform wake-up dominates.
- The background question-brewing thread only runs while the instance is awake (i.e., while someone is playing). If a freshly woken instance has an empty pool, the quest starts instantly from the offline bank and the AI session is ready next time — same graceful degradation as the CLI.
- Free Supabase projects pause after ~1 week of inactivity — see the database setup section above.

## Security

This repo is public. A few things worth knowing if you're deploying your own copy:

- **No secrets belong in this repo.** `.env`, `.env.local`, and `.vercel/` are gitignored; `.env.example` holds placeholder values only. Never commit a real API key, database password, or deploy token — if one leaks into git history, rotate it immediately (removing the file in a later commit does not remove it from history).
- **`SYNC_TOKEN`** gates the CLI sync endpoint (`POST /api/v1/progress`), the reports endpoint (`GET`/`DELETE /api/v1/reports`), which contains question text and kids' answers, and the activity endpoint (`GET /api/v1/activity`), which contains their session history. It's optional for a small family deploy behind an obscure URL, but set it before sharing the app or the backend URL more broadly.
- **`CORS_ORIGINS`** defaults to allowing any origin, which is convenient while standing things up but means any website could call your API from a visitor's browser. Set it to your actual Vercel URL for a real deploy.
- **Player auth**: every player sets a secret password (+ a hint only they understand); logging in issues a bearer token (`X-Player-Token`) required on all player-scoped endpoints. Passwords are stored PBKDF2-hashed; tokens are stored hashed and die when the secret changes. Players imported from the CLI have no secret yet and remain open until their first web login forces them to create one. A locked-out kid can notify the game developers from the login screen; a parent resets with `POST /api/v1/players/{id}/secret/reset` (gated by `SYNC_TOKEN` when set).
- **Rate limiting** (in-memory, per IP): 240 req/min globally, 5 login attempts/min per player, 5 new profiles/hour, and hourly caps on the endpoints that spend MiniMax credits (session starts, challenges, AI probes).
- **The MiniMax key stays server-side** (never sent to the browser) and generation prompts explicitly forbid instructions for anything dangerous even when covering safety-adjacent Expedition topics (chemicals, venom) — see `quest/ai.py` and `quest/expeditions.py`.
- **Deploy scripts and tokens:** `scripts/deploy_*.sh` take platform API tokens as environment variables, never as committed files. Treat a Render/Vercel/Supabase token as a password to that whole account — after using one to set up infrastructure, delete it from the platform's dashboard.

## Notes

- Never commit `.env` (already gitignored). Each twin's machine gets its own `.env` and its own `data/` profile for CLI play; the web app instead keeps one profile per player in the backend's database, shared across whichever devices they log into.
- The offline pack in `bank.py` (165 questions) and `quest/expeditions.py` (36 trivia questions) is sized to comfortably outlast the AI catching up — add more if you expect long stretches without internet or MiniMax access.
