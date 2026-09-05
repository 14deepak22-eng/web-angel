"""
Single-user password auth via a signed cookie. Fine for a personal dashboard
behind HTTPS (which Render/Railway give you for free). Not meant for
multi-user or high-security use — don't reuse this for anything sensitive
beyond your own screener.
"""
import os

from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi import Request, HTTPException

SECRET_KEY = os.environ.get("SESSION_SECRET", "change-me-in-.env-to-something-random")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "")
COOKIE_NAME = "screener_session"
MAX_AGE_SECONDS = 7 * 24 * 3600  # 7 days

serializer = URLSafeTimedSerializer(SECRET_KEY)


def check_password(password: str) -> bool:
    if not DASHBOARD_PASSWORD:
        raise RuntimeError("DASHBOARD_PASSWORD is not set — set it in your .env before running.")
    return password == DASHBOARD_PASSWORD


def make_session_cookie() -> str:
    return serializer.dumps({"authed": True})


def is_valid_session(token: str) -> bool:
    if not token:
        return False
    try:
        data = serializer.loads(token, max_age=MAX_AGE_SECONDS)
        return bool(data.get("authed"))
    except (BadSignature, SignatureExpired):
        return False


def require_login(request: Request):
    token = request.cookies.get(COOKIE_NAME)
    if not is_valid_session(token):
        raise HTTPException(status_code=401, detail="Not logged in")
