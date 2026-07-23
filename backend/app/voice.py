"""Family voice chat: a tiny WebRTC switchboard.

Players who've reached config.VOICE_CHAT_MIN_LEVEL connect over a WebSocket;
the server tracks who's online and relays call requests, accept/decline,
SDP offers/answers, and ICE candidates between two players. The audio itself
flows browser-to-browser over WebRTC — it never touches this server, and the
only people reachable are the family roster (each side must be a logged-in
player past the unlock level).

The registry is in-memory, which is correct for the single-process uvicorn
we deploy; a restart just drops everyone back to the lobby.
"""
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from quest import config, profile as profile_mod

from . import engine

router = APIRouter()

_clients = {}  # pid -> WebSocket
_names = {}    # pid -> display name
_lock = asyncio.Lock()

# Client -> server -> peer message types we relay verbatim (plus from/name).
_RELAYED = {"call", "accept", "decline", "signal", "hangup"}


def unlocked(player):
    return profile_mod.level_info(player["xp"])[0] >= config.VOICE_CHAT_MIN_LEVEL


async def _send(ws, payload):
    try:
        await ws.send_json(payload)
        return True
    except Exception:
        return False


async def _broadcast_roster():
    online = [{"id": pid, "name": _names.get(pid, "?")} for pid in _clients]
    for ws in list(_clients.values()):
        await _send(ws, {"type": "roster", "online": online})


@router.websocket("/api/v1/voice/ws")
async def voice_ws(ws: WebSocket, token: str = ""):
    player = engine.player_for_token(token)
    if player is None:
        await ws.close(code=4401)
        return
    if not unlocked(player):
        await ws.close(code=4403)
        return
    pid = player["id"]

    await ws.accept()
    async with _lock:
        stale = _clients.pop(pid, None)  # a second tab replaces the first
        _clients[pid] = ws
        _names[pid] = player["name"]
    if stale is not None:
        try:
            await stale.close()
        except Exception:
            pass
    await _broadcast_roster()

    try:
        while True:
            msg = await ws.receive_json()
            if not isinstance(msg, dict) or msg.get("type") not in _RELAYED:
                continue
            to = str(msg.get("to", ""))
            peer = _clients.get(to)
            if peer is None:
                await _send(ws, {"type": "peer-offline", "to": to})
                continue
            await _send(peer, {**msg, "from": pid,
                               "from_name": _names.get(pid, "?")})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass  # malformed frame or dropped socket — clean up below either way
    finally:
        async with _lock:
            if _clients.get(pid) is ws:
                _clients.pop(pid, None)
                _names.pop(pid, None)
        await _broadcast_roster()
