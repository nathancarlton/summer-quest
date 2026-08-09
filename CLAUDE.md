# Summer Quest — session notes

Daily 15-minute learning game for incoming 6th graders. CLI (`quest/`) and web
(React `frontend/` on Vercel + FastAPI `backend/` on Render + Supabase
Postgres) share one game engine. Full docs in README.md.

## ⚠️ Pending checks — do these / remind the dev before new feature work

- [ ] **Reading Room: quick visual check of the eight books.** Parser v5 was
  tested against the REAL text of all eight books (fetched via GITenberg
  GitHub mirrors — older editions than the live gutenberg.org files, plus a
  synthetic current-edition fixture) and every one split into its exact
  chapter count with proper titles. Remaining risk is small edition drift,
  so: open each book once in the deployed app and glance at chapter list +
  first page. If one looks weird, tune `_split_chapters()` in
  `backend/app/books.py` and bump `PARSER_VERSION` (auto re-parses on next
  open). Check off / delete this item when all eight look right.

## Backlog — ideas raised but not built

Not commitments; a place so good ideas stop living in chat scrollback.

- **Parent/family accounts (multi-family).** Raised for sharing the game with
  the friends' families. Today everything is ONE family: `list_players()`
  returns every player to the login roster, the leaderboard ranks all of
  them together, the Parent Zone key is a single shared `SYNC_TOKEN`, and
  the Family Phone connects anyone to anyone. Sharing as-is would show other
  families' kids' names, XP, activity, and reset buttons to each other.
  What it needs, roughly in order: a `family` record; `family_id` on each
  player; roster/leaderboard/voice/activity scoped by it; a per-family
  parent login replacing the one global admin key (the current key becomes
  the developer's superuser). The GLOBAL pieces should stay global on
  purpose — the shared question bank, the blocklist, and cached books all
  get better the more families use them. Note the blocklist means one
  family's report pulls a question from everyone; fine, but worth deciding
  deliberately.
- **Real book illustrations.** Gutenberg publishes an illustrated HTML
  edition per book (Denslow's Oz plates, Tenniel's Alice); the plain text we
  parse only has `[Illustration]` markers, now stripped. Would need: fetch
  the images edition, map pictures to chapters, and either hotlink
  gutenberg.org (discouraged, fragile) or cache the bytes and serve them
  from our own domain (right answer, costs Supabase storage). Untestable
  from the cloud sandbox — gutenberg.org is blocked there, so build it from
  a machine that can reach it.
- **Dependabot alert** on the default branch (one moderate, likely a Python
  dep) — nobody has looked yet.
- **Rotate the MiniMax API key.** The working key was pasted through chat
  during setup.

## Gotchas learned the hard way

- **Do NOT make the repo private without first connecting Render's GitHub
  App.** The Render service clones the repo anonymously (it was created via
  API against the public URL). Flipping the repo private breaks ALL backend
  deploys — Manual Deploy shows "unable to access your GitHub repository"
  and the deploy-hook workflow fails with HTTP 400 — while Vercel keeps
  working (it's app-connected), causing silent frontend/backend skew. This
  bit us on 2026-08-07. If privacy is wanted later: Render → Account
  Settings → connect GitHub → grant repo access, verify a deploy works,
  THEN flip visibility.
- The deploy workflow has a manual "Run workflow" button (GitHub → Actions)
  for re-kicking a failed deploy without pushing a dummy commit.

## Working agreements

- **Branch:** work directly on `main`. Push = deploy (Vercel via git
  integration; Render via `.github/workflows/deploy-backend.yml` calling the
  deploy hook). Verify backend freshness anytime: the `commit` field at
  `GET https://summer-quest-api-ebns.onrender.com/`.
- **Parallel sessions collide:** cloud session + local session both push to
  `main`. Pull before starting, push when stopping.
- **Env/config changes** (SYNC_TOKEN, MINIMAX_MODEL, QUESTION_SECONDS…):
  `bash scripts/deploy_render.sh` with the vars exported, or the Render
  dashboard Environment tab. Code changes need neither.
- **Testing habits used throughout:** engine-level tests with mocked AI/fetch
  (no MiniMax calls from dev), then `npm run build`, then a headless-Chromium
  pass of the real UI against a local uvicorn. Local SQLite is automatic when
  `DATABASE_URL` is unset; `rm -rf data/` resets it.
- **Parent Zone** (`/api/v1/reports`, `/api/v1/activity`) is gated by
  `SYNC_TOKEN` and holds kids' session history — never widen that gate, and
  keep new parent-only data behind `_require_reports_auth`.
- **Activity logging writes on session boundaries only** (login/logout,
  start/finish, chapter open) — never per answer. The answer path's latency
  is the thing users feel; don't add store writes to it.
- **Open-ended written tasks** ("write three X, separated by commas") are
  detected in `quest/ai.py` (`_is_open_ended`) and graded against the TASK,
  not the stored answer — which is one of many valid responses. Anything
  countable is counted in Python (`_item_check`) and given to the grader as
  fact; grader feedback must never mention the answer on file. If MiniMax
  keeps fumbling these, the lever is the generation prompt: stop asking for
  learner-invented content and keep short answers determinate.
- **Never generate questions client-side or ship answers to the browser**;
  grading, auth, and rate limits live server-side. Favorites stay impersonal
  (things, never people). New AI question paths must go through the
  confusion/length-tell filters and the `verify_mc` audit before serving
  (see `quest/ai.py` + the serve gate in `backend/app/engine.py`).
