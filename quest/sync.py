"""Sync stub for the future Render-hosted API.

If SYNC_URL is set, POSTs session summaries. Failed/offline posts are queued
locally and retried on next run. Silent by design — never blocks the kid.

Future backend contract (POST {SYNC_URL}/api/v1/progress):
  headers: Authorization: Bearer {SYNC_TOKEN}
  body: {"profile": {...full profile...}, "session": {...session summary...}}
"""
import json

import requests

from . import config


def _post(payload):
    resp = requests.post(
        f"{config.SYNC_URL.rstrip('/')}/api/v1/progress",
        headers={"Authorization": f"Bearer {config.SYNC_TOKEN}"},
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()


def _queue(payload):
    with config.SYNC_QUEUE_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")


def flush_queue():
    """Retry queued payloads. Returns number successfully sent."""
    if not config.SYNC_URL or not config.SYNC_QUEUE_PATH.exists():
        return 0
    lines = config.SYNC_QUEUE_PATH.read_text(encoding="utf-8").splitlines()
    remaining, sent = [], 0
    for line in lines:
        try:
            _post(json.loads(line))
            sent += 1
        except Exception:
            remaining.append(line)
    config.SYNC_QUEUE_PATH.write_text(
        "\n".join(remaining) + ("\n" if remaining else ""), encoding="utf-8"
    )
    return sent


def push(profile, session_summary):
    """Send progress. Queues on failure. Returns 'sent'|'queued'|'disabled'."""
    payload = {"profile": profile, "session": session_summary}
    if not config.SYNC_URL:
        return "disabled"
    try:
        _post(payload)
        return "sent"
    except Exception:
        _queue(payload)
        return "queued"
