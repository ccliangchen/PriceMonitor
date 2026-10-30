import secrets

from fastapi import Header, HTTPException, Request


def require_token(
    request: Request,
    authorization: str | None = Header(default=None),
) -> None:
    expected = request.app.state.settings.token
    if not expected:
        raise HTTPException(status_code=500, detail="Server token is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    provided = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid bearer token")
