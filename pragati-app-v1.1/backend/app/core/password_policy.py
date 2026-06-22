"""
Password policy validation.

Rules:
- minimum length (config-driven, default 10)
- at least one uppercase, one lowercase, one digit, one symbol
- not in a small denylist of obvious-bad choices
- not the username
"""
import re
from .config import settings

_COMMON_BAD = {
    "password", "password1", "password123", "admin", "admin123", "qwerty",
    "12345678", "letmein", "welcome", "iloveyou", "monkey", "pragati", "pragati123",
}


class PasswordPolicyError(ValueError):
    pass


def validate_password(password: str, username: str = "") -> None:
    """Raise PasswordPolicyError with a human-readable message on violation."""
    if not isinstance(password, str):
        raise PasswordPolicyError("Password must be a string")

    if len(password) < settings.password_min_length:
        raise PasswordPolicyError(
            f"Password must be at least {settings.password_min_length} characters"
        )

    if len(password) > 128:
        raise PasswordPolicyError("Password must be at most 128 characters")

    if password.lower() in _COMMON_BAD:
        raise PasswordPolicyError("Password is too common — pick something less guessable")

    if username and password.lower() == username.lower():
        raise PasswordPolicyError("Password must not be the same as the username")

    if not re.search(r"[a-z]", password):
        raise PasswordPolicyError("Password must contain at least one lowercase letter")
    if not re.search(r"[A-Z]", password):
        raise PasswordPolicyError("Password must contain at least one uppercase letter")
    if not re.search(r"\d", password):
        raise PasswordPolicyError("Password must contain at least one digit")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise PasswordPolicyError("Password must contain at least one symbol (e.g. !@#$)")
