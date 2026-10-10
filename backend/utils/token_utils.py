"""
Token utilities for generating secure, single-use interview tokens.

Uses itsdangerous to create signed, time-limited tokens that contain
a candidate_id and company_id. These tokens are verified publicly
without needing JWT or database lookups for core validation.
"""

import os
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "aurax-ai-super-secret-key-2026-change-in-prod")
INTERVIEW_TOKEN_MAX_AGE = 7 * 24 * 60 * 60  # 7 days in seconds
PASSWORD_RESET_TOKEN_MAX_AGE = 60 * 60  # 1 hour

# Separate salt so password-reset tokens can never be replayed as
# interview tokens (or vice versa) even though they share the secret.
_RESET_SALT = "password-reset-v1"
_INTERVIEW_SALT = "interview-v1"


def generate_interview_token(candidate_id: str, company_id: str) -> str:
    """
    Generate a signed, single-use interview token that expires in 7 days.
    
    Args:
        candidate_id: MongoDB ObjectId as string
        company_id: MongoDB ObjectId as string
    
    Returns:
        Signed token string safe for URLs
    """
    serializer = URLSafeTimedSerializer(SECRET_KEY, salt=_INTERVIEW_SALT)
    return serializer.dumps({
        "candidate_id": candidate_id,
        "company_id": company_id
    })


def verify_interview_token(token: str) -> dict:
    """
    Verify and decode an interview token.
    
    Args:
        token: Token from URL or query string
    
    Returns:
        Dict with candidate_id and company_id if valid
    
    Raises:
        SignatureExpired: if token has expired
        BadSignature: if token is invalid or tampered with
    """
    serializer = URLSafeTimedSerializer(SECRET_KEY, salt=_INTERVIEW_SALT)
    try:
        data = serializer.loads(token, max_age=INTERVIEW_TOKEN_MAX_AGE)
        return data
    except SignatureExpired:
        raise SignatureExpired("Interview link has expired. Please request a new one.")
    except BadSignature:
        raise BadSignature("Invalid or tampered interview link.")


def generate_password_reset_token(company_id: str) -> str:
    """
    Generate a signed password-reset token that expires in 1 hour.
    """
    serializer = URLSafeTimedSerializer(SECRET_KEY, salt=_RESET_SALT)
    return serializer.dumps({"company_id": company_id, "purpose": "password_reset"})


def verify_password_reset_token(token: str) -> dict:
    """
    Verify and decode a password-reset token.

    Returns:
        Dict with company_id if valid

    Raises:
        SignatureExpired: if the link is older than 1 hour
        BadSignature: if the token is invalid, tampered with, or was
            generated for a different purpose
    """
    serializer = URLSafeTimedSerializer(SECRET_KEY, salt=_RESET_SALT)
    try:
        data = serializer.loads(token, max_age=PASSWORD_RESET_TOKEN_MAX_AGE)
    except SignatureExpired:
        raise SignatureExpired("This reset link has expired. Please request a new one.")
    except BadSignature:
        raise BadSignature("Invalid or tampered reset link.")
    if data.get("purpose") != "password_reset":
        raise BadSignature("Invalid reset token purpose.")
    return data
