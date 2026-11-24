from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..database import get_db
from ..middleware.auth import bearer, create_token, current_user, decode_token, verify_password
from ..models import RevokedToken, User
from ..schemas import LoginIn, RefreshIn
from ..utils.helpers import user_dict
from ..services.auth_services import authenticate
from ..services import login_limiter

router = APIRouter(prefix="/auth", tags=["Authentication"])

@router.post("/login")
def login(data: LoginIn, request: Request, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else None
    wait = login_limiter.retry_after(ip, data.username)
    if wait:
        raise HTTPException(429, "Too many failed sign-in attempts. Try again later.", headers={"Retry-After": str(wait)})
    user = authenticate(db, data.username, data.password)
    if not user:
        login_limiter.record_failure(ip, data.username)
        raise HTTPException(401, "Invalid username or password")
    login_limiter.record_success(ip, data.username)
    if data.role is not None and user.role != data.role:
        raise HTTPException(403, "This account does not match the selected designation. Choose your assigned role and sign in again.")
    return {"access_token": create_token(user), "refresh_token": create_token(user, "refresh"),
            "token_type": "bearer", "user": user_dict(user)}

@router.post("/refresh")
def refresh(data: RefreshIn | None = None, credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)):
    if not data and not credentials: raise HTTPException(401, "Authentication required")
    payload = decode_token(data.refresh_token if data else credentials.credentials)
    if data and payload.get("type") != "refresh": raise HTTPException(401, "Refresh token required")
    if not data and payload.get("type") != "access": raise HTTPException(401, "Access token required")
    if db.scalar(select(RevokedToken).where(RevokedToken.jti == payload.get("jti"))):
        raise HTTPException(401, "Token has been revoked")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.active or user.token_version != payload.get("ver"): raise HTTPException(401, "Token is stale")
    return {"access_token": create_token(user), "token_type": "bearer"}

@router.post("/logout")
def logout(credentials: HTTPAuthorizationCredentials = Depends(bearer), user: User = Depends(current_user), db: Session = Depends(get_db)):
    payload = decode_token(credentials.credentials)
    db.add(RevokedToken(jti=payload["jti"], expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc).replace(tzinfo=None)))
    user.token_version += 1  # End existing access and refresh sessions.
    db.commit()
    return {"message": "Logged out"}

@router.get("/me")
def me(user: User = Depends(current_user)): return user_dict(user)


