from datetime import datetime, timedelta, timezone
from typing import Callable
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..config import get_settings
from ..database import get_db
from ..models import RevokedToken, User
from ..branching import apply_scope

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer = HTTPBearer(auto_error=False)
settings = get_settings()

def hash_password(value: str) -> str: return pwd.hash(value)
def verify_password(value: str, hashed: str) -> bool: return pwd.verify(value, hashed)

def create_token(user: User, token_type: str = "access") -> str:
    delta = timedelta(minutes=settings.access_token_minutes) if token_type == "access" else timedelta(days=settings.refresh_token_days)
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user.id), "role": user.role, "type": token_type, "ver": user.token_version,
               "iat": now, "exp": now + delta, "jti": f"{user.id}-{token_type}-{now.timestamp()}"}
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

def current_user(request: Request, credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not credentials: raise HTTPException(status_code=401, detail="Authentication required")
    data = decode_token(credentials.credentials)
    if data.get("type") != "access": raise HTTPException(status_code=401, detail="Access token required")
    if db.scalar(select(RevokedToken).where(RevokedToken.jti == data.get("jti"))):
        raise HTTPException(status_code=401, detail="Token has been revoked")
    user = db.get(User, int(data["sub"]))
    if not user or not user.active or user.token_version != data.get("ver"):
        raise HTTPException(status_code=401, detail="User is inactive or token is stale")
    # Directors may pick a branch with the X-Branch-Id header; everyone else works in their own.
    apply_scope(db, user, request.headers.get("X-Branch-Id"))
    return user

def require_roles(*roles: str) -> Callable:
    def dependency(user: User = Depends(current_user)) -> User:
        if user.role not in roles: raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return dependency
