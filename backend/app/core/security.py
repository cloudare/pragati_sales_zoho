"""Password hashing, JWT, refresh tokens, TOTP 2FA."""
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
import bcrypt
import pyotp
from jose import jwt, JWTError
from .config import settings


def _to_bytes(pw: str) -> bytes:
    """bcrypt's 72-byte limit — truncate explicitly."""
    return pw.encode("utf-8")[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_to_bytes(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_to_bytes(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------- ACCESS TOKEN (short-lived, stateless JWT) ----------------
def create_access_token(data: dict) -> str:
    payload = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload.update({"exp": expire, "typ": "access"})
    return jwt.encode(payload, settings.app_secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.app_secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None


# ---------------- REFRESH TOKEN (long-lived, server-side revocable) ----------------
def generate_refresh_token() -> tuple[str, str, datetime]:
    """
    Returns (raw_token, hash, expires_at).
    Raw token is given to the client; hash is stored in DB.
    """
    raw = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    return raw, token_hash, expires_at


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ---------------- TEMP TOKEN (for 2FA interstitial: pwd verified, 2FA pending) ----------------
def create_2fa_temp_token(user_id: int) -> str:
    """5-minute temp token that ONLY proves password was correct.
    Cannot be used to access any API except /api/auth/2fa/verify."""
    payload = {
        "sub": str(user_id),
        "typ": "2fa_pending",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    return jwt.encode(payload, settings.app_secret_key, algorithm=settings.algorithm)


def decode_2fa_temp_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.app_secret_key, algorithms=[settings.algorithm])
        if payload.get("typ") != "2fa_pending":
            return None
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        return None


# ---------------- TOTP 2FA ----------------
def generate_totp_secret() -> str:
    return pyotp.random_base32()


def totp_provisioning_uri(secret: str, username: str, issuer: str = "Pragati Sales") -> str:
    """The otpauth:// URL that gets encoded to a QR code."""
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=issuer)


def verify_totp(secret: str, code: str) -> bool:
    """Verify a 6-digit TOTP code. Allows +/- 1 step (30s window each side) for clock drift."""
    if not secret or not code:
        return False
    try:
        return pyotp.TOTP(secret).verify(code.strip(), valid_window=1)
    except Exception:
        return False
