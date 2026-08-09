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
- **Never generate questions client-side or ship answers to the browser**;
  grading, auth, and rate limits live server-side. Favorites stay impersonal
  (things, never people). New AI question paths must go through the
  confusion/length-tell filters and the `verify_mc` audit before serving
  (see `quest/ai.py` + the serve gate in `backend/app/engine.py`).
