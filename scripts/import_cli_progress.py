#!/usr/bin/env python3
"""Upload a kid's CLI progress to the web backend, one machine at a time.

The CLI stores everything locally in data/ (profile.json + history.jsonl).
This sends it all to the backend so the same adventurer — XP, streak, badges,
favorites, and which questions they've already mastered — shows up in the web
app's player picker and carries on from where the CLI left off.

Usage, from the repo root on the kid's machine (venv active):
    python3 scripts/import_cli_progress.py https://summer-quest-api-ebns.onrender.com

Options:
    --data DIR    read a different data directory (default: ./data)
    --force       re-import even if this player already exists on the backend
                  (replaces their online copy with this machine's copy)
If the backend has SYNC_TOKEN set, export SYNC_TOKEN=... first.
"""
import argparse
import json
import os
import sys
from pathlib import Path

import requests


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("base_url", help="backend URL, e.g. https://summer-quest-api-ebns.onrender.com")
    ap.add_argument("--data", default="data")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")
    data_dir = Path(args.data)

    profile_path = data_dir / "profile.json"
    if not profile_path.exists():
        sys.exit(f"No profile at {profile_path} — run from the repo root on the kid's machine.")
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    name, pid = profile.get("name", "?"), profile.get("id")
    print(f"Importing {name} ({pid})")
    print(f"       → {base}")

    headers = {}
    if os.environ.get("SYNC_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['SYNC_TOKEN']}"

    # First request may take ~30s if the free backend is waking up.
    print("Checking the backend (may take ~30s if it's waking up)…")
    r = requests.get(f"{base}/api/v1/players/{pid}", timeout=90)
    if r.status_code == 200 and not args.force:
        sys.exit(
            f"{name} already exists on the backend — re-run with --force to overwrite\n"
            "(any web progress made since the last import would be replaced by this\n"
            "machine's copy, and history sessions would be re-appended)."
        )

    sessions = []
    history_path = data_dir / "history.jsonl"
    if history_path.exists():
        for line in history_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    sessions.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    # Profile first (authoritative), then history one summary at a time —
    # the same contract the CLI's own sync uses (see quest/sync.py).
    requests.post(
        f"{base}/api/v1/progress", json={"profile": profile, "session": None},
        headers=headers, timeout=90,
    ).raise_for_status()
    for i, s in enumerate(sessions, 1):
        requests.post(
            f"{base}/api/v1/progress", json={"profile": profile, "session": s},
            headers=headers, timeout=90,
        ).raise_for_status()
        print(f"  session {i}/{len(sessions)} uploaded")

    print(f"\nDone: profile + {len(sessions)} session(s) imported.")
    print(f"Open the web app and pick “{name}” in the player list — XP, streak,")
    print("badges, favorites, and mastered questions all carried over.")


if __name__ == "__main__":
    main()
