"""
Authentication routes - hardened.

Endpoints:
  POST  /api/auth/login                Login (with optional 2FA interstitial)
  POST  /api/auth/refresh              Use refresh token to get a new access token
  POST  /api/auth/logout               Revoke current refresh token
  POST  /api/auth/change-password      Self-change password (also clears must_change_password)
  GET   /api/auth/me                   Current user
  POST  /api/auth/users                Admin creates user
  GET   /api/auth/users                Admin lists users
  POST  /api/auth/users/{id}/reset-password  Admin resets a user's password (sets must_change=true)
  POST  /api/auth/users/{id}/unlock    Admin unlocks a locked account
  POST  /api/auth/2fa/setup            Begin 2FA setup (returns secret + otpauth URL)
  POST  /api/auth/2fa/enable           Verify code, enable 2FA on account
  POST  /api/auth/2fa/disable          Disable 2FA (requires password)
  POST  /api/auth/2fa/verify           Login completion when 2FA required
"""
from datetime import datetime, timezone, timedelta
from io import BytesIO
import base64

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from ..core.database import get_db
from ..core.config import settings
from ..core.security import (
    verify_password, hash_password, create_access_token,
    generate_refresh_token, hash_refresh_token,
    create_2fa_temp_token, decode_2fa_temp_token,
    generate_totp_secret, totp_provisioning_uri, verify_totp,
)
from ..core.password_policy import validate_password, PasswordPolicyError
from ..core.deps import get_current_user, require_roles
from ..models import User, UserRole, RefreshToken, AuditLog

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ============================== schemas ==============================
class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    user: dict
    must_change_password: bool = False
    requires_2fa_setup: bool = False  # role requires 2FA but user has not set it up


class TwoFARequiredResponse(BaseModel):
    requires_2fa: bool = True
    temp_token: str  # 5-minute token to complete login


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    full_name: str = Field(min_length=1, max_length=128)
    password: str
    role: UserRole = UserRole.sales


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


class ResetPasswordRequest(BaseModel):
    new_password: str


class Verify2FARequest(BaseModel):
    temp_token: str
    code: str


class Enable2FARequest(BaseModel):
    code: str


class Disable2FARequest(BaseModel):
    password: str


# ============================== helpers ==============================
def _client_meta(request: Request) -> tuple[str, str]:
    """Best-effort IP + user-agent for audit logs."""
    ip = request.client.host if request.client else "?"
    # honour X-Forwarded-For if behind nginx; take first
    xff = request.headers.get("x-forwarded-for")
    if xff:
        ip = xff.split(",")[0].strip()
    ua = (request.headers.get("user-agent") or "")[:240]
    return ip, ua


def _log(db: Session, *, action: str, actor_id: int | None, details: dict):
    db.add(AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type="auth",
        entity_id=actor_id or 0,
        details=details,
    ))
    db.commit()


def _issue_session(db: Session, user: User, request: Request) -> dict:
    """Create access + refresh tokens and a DB row for the refresh token."""
    ip, ua = _client_meta(request)
    access = create_access_token({
        "sub": str(user.id), "role": user.role.value, "username": user.username,
    })
    raw, token_hash, expires_at = generate_refresh_token()
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
        user_agent=ua,
        ip_address=ip,
    ))
    user.last_login_at = datetime.now(timezone.utc)
    user.last_login_ip = ip
    user.failed_login_count = 0
    user.locked_until = None
    db.commit()

    requires_2fa_setup = (
        user.role.value in settings.require_2fa_roles_list and not user.totp_enabled
    )
    return {
        "access_token": access,
        "refresh_token": raw,
        "user": {
            "id": user.id, "username": user.username,
            "full_name": user.full_name, "role": user.role.value,
            "totp_enabled": user.totp_enabled,
        },
        "must_change_password": user.must_change_password,
        "requires_2fa_setup": requires_2fa_setup,
    }


def _register_failed_login(db: Session, user: User | None, username: str, ip: str, ua: str):
    """Increment counter, possibly lock, write audit."""
    if user:
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= settings.max_failed_login_attempts:
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=settings.lockout_minutes)
        db.commit()
    db.add(AuditLog(
        actor_id=user.id if user else None,
        action="login.failed",
        entity_type="auth",
        entity_id=user.id if user else 0,
        details={"username": username, "ip": ip, "ua": ua,
                 "fail_count": user.failed_login_count if user else None,
                 "locked": bool(user and user.locked_until)},
    ))
    db.commit()


# ============================== LOGIN ==============================
@router.post("/login")
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    ip, ua = _client_meta(request)
    user = db.query(User).filter(User.username == form.username).first()

    # Check lockout before checking password (don't leak which is which)
    if user and user.locked_until and user.locked_until > datetime.now(timezone.utc):
        mins = int((user.locked_until - datetime.now(timezone.utc)).total_seconds() / 60) + 1
        raise HTTPException(status_code=423, detail=f"Account locked. Try again in {mins} minute(s).")

    if not user or not verify_password(form.password, user.password_hash):
        _register_failed_login(db, user, form.username, ip, ua)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if not user.is_active:
        _log(db, action="login.failed", actor_id=user.id,
             details={"reason": "disabled", "ip": ip, "ua": ua})
        raise HTTPException(status_code=401, detail="User disabled")

    # Password correct. If 2FA enabled, return interstitial.
    if user.totp_enabled:
        _log(db, action="login.password_ok_2fa_pending", actor_id=user.id,
             details={"ip": ip, "ua": ua})
        return TwoFARequiredResponse(temp_token=create_2fa_temp_token(user.id))

    # Otherwise full session.
    payload = _issue_session(db, user, request)
    _log(db, action="login.success", actor_id=user.id,
         details={"ip": ip, "ua": ua, "method": "password"})
    return LoginResponse(**payload)


# ============================== 2FA VERIFY (login completion) ==============================
@router.post("/2fa/verify")
def two_fa_verify(req: Verify2FARequest, request: Request, db: Session = Depends(get_db)):
    ip, ua = _client_meta(request)
    uid = decode_2fa_temp_token(req.temp_token)
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid or expired 2FA token")
    user = db.query(User).filter(User.id == uid).first()
    if not user or not user.is_active or not user.totp_enabled:
        raise HTTPException(status_code=401, detail="2FA not enabled for this user")
    if not verify_totp(user.totp_secret, req.code):
        _log(db, action="login.2fa_failed", actor_id=user.id, details={"ip": ip, "ua": ua})
        # Count toward lockout
        _register_failed_login(db, user, user.username, ip, ua)
        raise HTTPException(status_code=401, detail="Invalid 2FA code")
    payload = _issue_session(db, user, request)
    _log(db, action="login.success", actor_id=user.id,
         details={"ip": ip, "ua": ua, "method": "2fa"})
    return LoginResponse(**payload)


# ============================== REFRESH ==============================
@router.post("/refresh")
def refresh(req: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    token_hash = hash_refresh_token(req.refresh_token)
    rt = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
    if not rt or rt.revoked_at is not None or rt.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    user = db.query(User).filter(User.id == rt.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User disabled")

    # Rotate: revoke old, issue new
    rt.revoked_at = datetime.now(timezone.utc)
    payload = _issue_session(db, user, request)
    return LoginResponse(**payload)


# ============================== LOGOUT ==============================
@router.post("/logout")
def logout(req: LogoutRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if req.refresh_token:
        token_hash = hash_refresh_token(req.refresh_token)
        rt = db.query(RefreshToken).filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.user_id == user.id,
        ).first()
        if rt and rt.revoked_at is None:
            rt.revoked_at = datetime.now(timezone.utc)
            db.commit()
    _log(db, action="logout", actor_id=user.id, details={})
    return {"ok": True}


# ============================== CHANGE PASSWORD ==============================
@router.post("/change-password")
def change_password(req: ChangePasswordRequest, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    if not verify_password(req.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    try:
        validate_password(req.new_password, username=user.username)
    except PasswordPolicyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if verify_password(req.new_password, user.password_hash):
        raise HTTPException(status_code=400, detail="New password must differ from current password")

    user.password_hash = hash_password(req.new_password)
    user.must_change_password = False
    user.password_changed_at = datetime.now(timezone.utc)
    # Revoke all refresh tokens — force re-login on other devices
    db.query(RefreshToken).filter(
        RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None)
    ).update({"revoked_at": datetime.now(timezone.utc)})
    db.commit()
    _log(db, action="password.changed", actor_id=user.id, details={})
    return {"ok": True}


# ============================== ME ==============================
@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {
        "id": user.id, "username": user.username, "full_name": user.full_name,
        "role": user.role.value, "totp_enabled": user.totp_enabled,
        "must_change_password": user.must_change_password,
    }


# ============================== USERS (admin) ==============================
@router.post("/users", dependencies=[Depends(require_roles(UserRole.admin))])
def create_user(req: CreateUserRequest, db: Session = Depends(get_db),
                actor: User = Depends(get_current_user)):
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    try:
        validate_password(req.password, username=req.username)
    except PasswordPolicyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    u = User(
        username=req.username,
        full_name=req.full_name,
        password_hash=hash_password(req.password),
        role=req.role,
        must_change_password=True,  # force change on first login
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    _log(db, action="user.created", actor_id=actor.id,
         details={"new_user_id": u.id, "username": u.username, "role": u.role.value})
    return {"id": u.id, "username": u.username, "role": u.role.value}


@router.get("/users", dependencies=[Depends(require_roles(UserRole.admin))])
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [{
        "id": u.id, "username": u.username, "full_name": u.full_name,
        "role": u.role.value, "is_active": u.is_active,
        "totp_enabled": u.totp_enabled,
        "must_change_password": u.must_change_password,
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        "locked": bool(u.locked_until and u.locked_until > datetime.now(timezone.utc)),
    } for u in users]


@router.post("/users/{user_id}/reset-password",
             dependencies=[Depends(require_roles(UserRole.admin))])
def reset_user_password(user_id: int, req: ResetPasswordRequest,
                        db: Session = Depends(get_db),
                        actor: User = Depends(get_current_user)):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        validate_password(req.new_password, username=target.username)
    except PasswordPolicyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    target.password_hash = hash_password(req.new_password)
    target.must_change_password = True
    target.password_changed_at = datetime.now(timezone.utc)
    # Revoke all of target's refresh tokens
    db.query(RefreshToken).filter(
        RefreshToken.user_id == target.id, RefreshToken.revoked_at.is_(None)
    ).update({"revoked_at": datetime.now(timezone.utc)})
    db.commit()
    _log(db, action="user.password_reset", actor_id=actor.id,
         details={"target_user_id": target.id})
    return {"ok": True}


@router.post("/users/{user_id}/unlock",
             dependencies=[Depends(require_roles(UserRole.admin))])
def unlock_user(user_id: int, db: Session = Depends(get_db),
                actor: User = Depends(get_current_user)):
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    target.failed_login_count = 0
    target.locked_until = None
    db.commit()
    _log(db, action="user.unlocked", actor_id=actor.id, details={"target_user_id": target.id})
    return {"ok": True}


# ============================== 2FA SETUP ==============================
@router.post("/2fa/setup")
def two_fa_setup(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Generate a fresh secret and return QR code (base64 PNG).
    Not yet enabled — call /2fa/enable with a valid code to activate.
    """
    if user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA is already enabled")
    secret = generate_totp_secret()
    user.totp_secret = secret  # stored but not enabled yet
    db.commit()
    uri = totp_provisioning_uri(secret, user.username)
    # Generate QR code PNG → base64
    img = qrcode.make(uri)
    buf = BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return {
        "secret": secret,
        "otpauth_uri": uri,
        "qr_png_base64": qr_b64,
    }


@router.post("/2fa/enable")
def two_fa_enable(req: Enable2FARequest, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    if user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA is already enabled")
    if not user.totp_secret:
        raise HTTPException(status_code=400, detail="No setup in progress — call /2fa/setup first")
    if not verify_totp(user.totp_secret, req.code):
        raise HTTPException(status_code=400, detail="Invalid code")
    user.totp_enabled = True
    user.totp_enabled_at = datetime.now(timezone.utc)
    db.commit()
    _log(db, action="2fa.enabled", actor_id=user.id, details={})
    return {"ok": True}


@router.post("/2fa/disable")
def two_fa_disable(req: Disable2FARequest, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    if not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Password is incorrect")
    if user.role.value in settings.require_2fa_roles_list:
        raise HTTPException(status_code=400,
                            detail=f"2FA is required for role '{user.role.value}'")
    user.totp_enabled = False
    user.totp_secret = None
    user.totp_enabled_at = None
    db.commit()
    _log(db, action="2fa.disabled", actor_id=user.id, details={})
    return {"ok": True}
