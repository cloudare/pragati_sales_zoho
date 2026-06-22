"""Auth dependencies for FastAPI."""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import List
from ..core.database import get_db
from ..core.security import decode_token
from ..models import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    cred_exc = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    payload = decode_token(token)
    if not payload:
        raise cred_exc
    user_id = payload.get("sub")
    if not user_id:
        raise cred_exc
    user = db.query(User).get(int(user_id))
    if not user or not user.is_active:
        raise cred_exc
    return user


def require_roles(*roles: UserRole):
    """Dependency factory that asserts user role is in the allowed set."""
    allowed = set(roles)

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role != UserRole.admin and user.role not in allowed:
            raise HTTPException(status_code=403, detail=f"Requires one of: {[r.value for r in allowed]}")
        return user

    return checker
