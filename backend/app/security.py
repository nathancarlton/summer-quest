"""Rate limiting + player secrets (password hashing, auth tokens).

Stdlib only — PBKDF2 for the kids' secret passwords, an in-memory
sliding-window rate limiter (fine on a single free-tier instance), and
opaque bearer tokens stored hashed in the kv store.
"""
import hashlib
import hmac
import secrets
import threading
import time
from collections import deque

from fastapi import HTTPException, Request


# ─── Rate limiting ───────────────────────────────────────────────────────────

class RateLimiter:
    """Sliding-window counter per key. In-memory: resets on restart, which is
    acceptable — its job is stopping bursts (password guessing, MiniMax cost
    abuse), not perfect accounting."""

    def __init__(self):
        self._hits = {}
        self._lock = threading.Lock()

    def check(self, key, limit, window_seconds):
        now = time.time()
        with self._lock:
            dq = self._hits.setdefault(key, deque())
            while dq and dq[0] <= now - window_seconds:
                dq.popleft()
            if len(dq) >= limit:
                raise HTTPException(
                    429, "Too many requests — take a breath and try again in a minute."
                )
            dq.append(now)
            if len(self._hits) > 5000:  # opportunistic cleanup of stale keys
                for k in [k for k, d in self._hits.items() if not d][:2500]:
                    self._hits.pop(k, None)


limiter = RateLimiter()


def client_ip(request: Request):
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:  # Render terminates TLS in front of us; first hop is the client
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(name, limit, window_seconds):
    """FastAPI dependency: per-IP limit for one endpoint family."""

    def dep(request: Request):
        limiter.check(f"{name}:{client_ip(request)}", limit, window_seconds)

    return dep


# ─── Secret passwords ────────────────────────────────────────────────────────

_ITERATIONS = 120_000


def hash_secret(secret, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", secret.encode("utf-8"), bytes.fromhex(salt), _ITERATIONS
    ).hex()
    return f"{salt}${digest}"


def verify_secret(secret, stored):
    try:
        salt, digest = (stored or "").split("$", 1)
        calc = hashlib.pbkdf2_hmac(
            "sha256", secret.encode("utf-8"), bytes.fromhex(salt), _ITERATIONS
        ).hex()
    except (ValueError, AttributeError):
        return False
    return hmac.compare_digest(calc, digest)


# ─── Auth tokens ─────────────────────────────────────────────────────────────

def new_token():
    return secrets.token_urlsafe(32)


def token_key(token):
    """Tokens are stored hashed, so a database leak doesn't leak logins."""
    return "token:" + hashlib.sha256(token.encode("utf-8")).hexdigest()
