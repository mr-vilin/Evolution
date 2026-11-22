"""Display information from the successful Feishu login, scoped to that session."""

import base64
import hashlib
import hmac
import json
from urllib.parse import urlsplit


_COOKIE_LIMIT = 3000


def _signature(secret: str, session_id: str, payload: str) -> str:
    value = f"admin_profile:{session_id}:{payload}".encode()
    return hmac.new(secret.encode(), value, hashlib.sha256).hexdigest()


def _encode(profile: dict) -> str:
    data = json.dumps(profile, ensure_ascii=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(data).decode("ascii")


def encode_admin_profile(identity: dict, secret: str, session_id: str) -> str:
    name = identity.get("name")
    name = name.strip()[:128] if isinstance(name, str) else ""
    avatar = identity.get("avatar_url")
    try:
        url = urlsplit(avatar) if isinstance(avatar, str) and len(avatar) < _COOKIE_LIMIT else None
    except ValueError:
        url = None
    profile = {
        "name": name or None,
        "avatar_url": avatar if url and url.scheme == "https" and url.hostname and not url.username else None,
    }
    payload = _encode(profile)
    if len(payload) + 65 > _COOKIE_LIMIT:
        profile["avatar_url"] = None
        payload = _encode(profile)
    return f"{payload}.{_signature(secret, session_id, payload)}"


def decode_admin_profile(cookie: str, secret: str, session_id: str) -> dict | None:
    if len(cookie) > _COOKIE_LIMIT or not cookie.isascii():
        return None
    payload, _, signature = cookie.partition(".")
    if not hmac.compare_digest(signature, _signature(secret, session_id, payload)):
        return None
    return json.loads(base64.urlsafe_b64decode(payload))
