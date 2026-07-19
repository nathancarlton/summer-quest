#!/usr/bin/env bash
# One-shot Render setup for the Summer Quest backend.
#
# Usage (from the repo root):
#   RENDER_KEY=rnd_xxx MINIMAX_API_KEY=xxx bash scripts/deploy_render.sh
#
# Optional extra env vars picked up if set: DATABASE_URL, CORS_ORIGINS, SYNC_TOKEN.
# Safe to re-run: if the service already exists, it updates env vars instead.
set -euo pipefail

: "${RENDER_KEY:?Set RENDER_KEY to your Render API key (rnd_...)}"

API=https://api.render.com/v1
auth=(-H "Authorization: Bearer $RENDER_KEY" -H "Content-Type: application/json")
REPO_URL="https://github.com/nathancarlton/summer-quest"
NAME="summer-quest-api"

echo "→ Looking up your Render account…"
OWNER_ID=$(curl -sS "${auth[@]}" "$API/owners" |
  python3 -c 'import sys,json; print(json.load(sys.stdin)[0]["owner"]["id"])')
echo "  owner: $OWNER_ID"

# Env vars to set on the service — only the ones present in this shell.
ENVVARS=$(python3 -c '
import json, os
keys = ("MINIMAX_API_KEY", "MINIMAX_BASE_URL", "MINIMAX_MODEL",
        "DATABASE_URL", "CORS_ORIGINS", "SYNC_TOKEN")
print(json.dumps([{"key": k, "value": os.environ[k]} for k in keys if os.environ.get(k)]))
')

echo "→ Checking for an existing $NAME service…"
EXISTING_ID=$(curl -sS "${auth[@]}" "$API/services?name=$NAME&limit=1" |
  python3 -c 'import sys,json
d = json.load(sys.stdin)
print(d[0]["service"]["id"] if d else "")')

if [ -n "$EXISTING_ID" ]; then
  echo "  found $EXISTING_ID — merging env vars and redeploying."
  # Merge with what's already on the service so a re-run with only some vars
  # exported never silently deletes the others (e.g. DATABASE_URL).
  CURRENT=$(curl -sS "${auth[@]}" "$API/services/$EXISTING_ID/env-vars?limit=100")
  MERGED=$(CURRENT="$CURRENT" ENVVARS="$ENVVARS" python3 -c '
import json, os
cur = json.loads(os.environ["CURRENT"])
merged = {}
for item in (cur if isinstance(cur, list) else []):
    ev = item.get("envVar", item)
    if isinstance(ev, dict) and "key" in ev:
        merged[ev["key"]] = ev.get("value", "")
for ev in json.loads(os.environ["ENVVARS"]):
    merged[ev["key"]] = ev["value"]
print(json.dumps([{"key": k, "value": v} for k, v in sorted(merged.items())]))
')
  curl -sS "${auth[@]}" -X PUT "$API/services/$EXISTING_ID/env-vars" -d "$MERGED" >/dev/null
  curl -sS "${auth[@]}" -X POST "$API/services/$EXISTING_ID/deploys" -d '{}' >/dev/null
  SERVICE_JSON=$(curl -sS "${auth[@]}" "$API/services/$EXISTING_ID")
else
  echo "→ Creating web service (free instance, Ohio)…"
  PAYLOAD=$(OWNER_ID="$OWNER_ID" ENVVARS="$ENVVARS" REPO_URL="$REPO_URL" NAME="$NAME" python3 -c '
import json, os
print(json.dumps({
    "type": "web_service",
    "name": os.environ["NAME"],
    "ownerId": os.environ["OWNER_ID"],
    "repo": os.environ["REPO_URL"],
    "branch": "main",
    "autoDeploy": "yes",
    "envVars": json.loads(os.environ["ENVVARS"]),
    "serviceDetails": {
        "runtime": "python",
        "region": "ohio",
        "plan": "free",
        "envSpecificDetails": {
            "buildCommand": "pip install -r requirements.txt",
            "startCommand": "uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT",
        },
    },
}))
')
  SERVICE_JSON=$(curl -sS "${auth[@]}" -X POST "$API/services" -d "$PAYLOAD")
fi

echo "$SERVICE_JSON" | python3 -c '
import json, sys
d = json.load(sys.stdin)
svc = d.get("service", d)
if "id" not in svc:
    print("\nRender answered with an error:")
    print(json.dumps(d, indent=2)[:2000])
    print("\nIf it says the repo was not found, the repo is private: open")
    print("dashboard.render.com, click New -> Web Service once to connect GitHub,")
    print("then re-run this script.")
    sys.exit(1)
url = (svc.get("serviceDetails") or {}).get("url") or "(url pending)"
print()
print("  service id:", svc["id"])
print("  dashboard:  https://dashboard.render.com/web/" + svc["id"])
print("  public URL:", url)
print()
print("First build is running — takes a few minutes on the free tier.")
print("When live, open " + url + "/ and expect {\"status\": \"healthy\"}")
'
