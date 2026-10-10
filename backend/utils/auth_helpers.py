import secrets
from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash, check_password_hash

def hash_password(password: str) -> str:
    """
    Hashes a plain-text password using Werkzeug's default PBKDF2/SHA256 method.
    """
    return generate_password_hash(password)

def verify_password(password: str, hashed_password: bool) -> bool:
    """
    Verifies a plain-text password against a stored hash.
    """
    return check_password_hash(hashed_password, password)

def generate_otp() -> str:
    """
    Generates a cryptographically secure 6-digit numeric OTP.
    (Previously used random.randint — not safe against prediction.)
    """
    return f"{secrets.randbelow(900000) + 100000}"

def otp_expiry_timestamp(minutes: int = 5) -> datetime:
    """
    Returns a timezone-aware datetime representing the OTP expiration.
    Default raised from 1 minute to 5 — 1 minute made it nearly unusable
    with real email delivery latency.
    """
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)
