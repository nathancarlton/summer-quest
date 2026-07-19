#!/usr/bin/env bash
# One-shot Vercel setup for the Summer Quest frontend.
#
# Usage (from the repo root, AFTER the Render backend exists):
#   VERCEL_TOKEN=vcp_xxx VITE_API_URL=https://summer-quest-api.onrender.com \
#     bash scripts/deploy_vercel.sh
#
# Safe to re-run: updates the env var and redeploys.
set -euo pipefail

: "${VERCEL_TOKEN:?Set VERCEL_TOKEN to your Vercel token (vcp_...)}"
: "${VITE_API_URL:?Set VITE_API_URL to your Render backend URL (no trailing slash)}"

cd "$(dirname "$0")/.."
PROJECT=summer-quest
REPO="nathancarlton/summer-quest"
VC=(npx --yes vercel@latest --token "$VERCEL_TOKEN")

echo "→ Linking (or creating) the $PROJECT project…"
"${VC[@]}" link --yes --project "$PROJECT"

echo "→ Setting Root Directory to frontend/ (needed for git auto-deploys)…"
curl -sS -X PATCH "https://api.vercel.com/v9/projects/$PROJECT" \
  -H "Authorization: Bearer $VERCEL_TOKEN" -H "Content-Type: application/json" \
  -d '{"rootDirectory": "frontend", "framework": "vite"}' >/dev/null

echo "→ Setting VITE_API_URL for production…"
"${VC[@]}" env rm VITE_API_URL production --yes >/dev/null 2>&1 || true
printf '%s' "$VITE_API_URL" | "${VC[@]}" env add VITE_API_URL production

echo "→ Deploying to production…"
DEPLOY_URL=$("${VC[@]}" deploy --prod --yes)

echo "→ Connecting the GitHub repo so every push auto-deploys…"
if "${VC[@]}" git connect "https://github.com/$REPO" --yes; then
  echo "  auto-deploy on git push is ON."
else
  echo "  Couldn't connect git automatically — Vercel's GitHub app probably"
  echo "  isn't installed on your GitHub account yet. One-time fix: open the"
  echo "  project on vercel.com → Settings → Git → Connect → pick $REPO."
fi

echo
echo "Frontend URL: $DEPLOY_URL"
echo
echo "Last step: lock the backend's CORS to this URL — re-run the Render script"
echo "with CORS_ORIGINS=$DEPLOY_URL (plus your other env vars), or set it in the"
echo "Render dashboard → Environment."
