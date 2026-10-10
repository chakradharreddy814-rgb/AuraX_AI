from datetime import datetime, timezone

from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required
from bson import ObjectId

from extensions import limiter
from utils.db import companies_collection, otp_collection, password_reset_collection
from utils.auth_helpers import (
    hash_password,
    verify_password,
    generate_otp,
    otp_expiry_timestamp,
)
from utils.auth_helper import get_current_company
from agents.email_sender import send_email

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _send_otp_email(to_email: str, company_name: str, otp: str) -> None:
    """
    Sends the verification code. Reuses Agent 4's send_email() (delivery
    only) — a 6-digit code doesn't need Gemini's content-generation layer,
    unlike candidate-facing shortlist/rejection emails.
    """
    subject = "Verify your AuraX AI account"
    body = (
        f"Hi {company_name},\n\n"
        f"Your verification code is: {otp}\n\n"
        f"This code expires in 1 minute. If you didn't request this, "
        f"you can safely ignore this email.\n\n"
        f"— AuraX AI"
    )
    send_email(to_email=to_email, subject=subject, body=body, from_name="AuraX AI")


# ---------------------------------------------------------------------------
# POST /api/auth/signup
# ---------------------------------------------------------------------------

@auth_bp.route("/signup", methods=["POST"])
@limiter.limit("10 per hour")
def signup():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    company_name = (data.get("company_name") or "").strip()
    full_name = (data.get("full_name") or "").strip()

    if not email or not password or not company_name or not full_name:
        return jsonify({
            "error": "email, password, company_name, and full_name are all required."
        }), 400

    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400

    if companies_collection.find_one({"email": email}):
        return jsonify({"error": "An account with this email already exists."}), 409

    company_doc = {
        "email": email,
        "password": hash_password(password),
        "company_name": company_name,
        "full_name": full_name,
        "is_verified": False,
        "company_logo_url": None,
        "created_at": datetime.now(timezone.utc),
    }

    try:
        result = companies_collection.insert_one(company_doc)
    except Exception as e:
        # Safety net for the rare race condition two near-simultaneous
        # signups with the same email could hit — the unique index on
        # email is the real guard; this just turns it into a clean 409.
        return jsonify({"error": f"Could not create account: {e}"}), 409

    company_id = str(result.inserted_id)

    otp = generate_otp()
    otp_collection.insert_one({
        "email": email,
        "otp": otp,
        "company_id": company_id,
        "expires_at": otp_expiry_timestamp(minutes=1),
    })

    email_error = None
    try:
        _send_otp_email(email, company_name, otp)
    except Exception as e:
        email_error = str(e)
        print(f"[auth/signup] Email send failed: {e}")

    return jsonify({
        "message": "Account created. Check your email for a verification code.",
        "company_id": company_id,
        **({"email_error": email_error} if email_error else {}),
    }), 201


# ---------------------------------------------------------------------------
# POST /api/auth/verify-otp
# ---------------------------------------------------------------------------

@auth_bp.route("/verify-otp", methods=["POST"])
@limiter.limit("20 per hour")
def verify_otp():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    submitted_otp = (data.get("otp") or "").strip()

    if not email or not submitted_otp:
        return jsonify({"error": "email and otp are required."}), 400

    record = otp_collection.find_one({"email": email, "otp": submitted_otp})

    # otp_collection has a TTL index on expires_at (see db.py), so an
    # expired OTP document is already auto-deleted by MongoDB — "not
    # found" here covers both "wrong code" and "expired code" for free.
    if not record:
        return jsonify({"error": "Invalid or expired code. Please request a new one."}), 400

    company = companies_collection.find_one_and_update(
        {"email": email},
        {"$set": {"is_verified": True}},
        return_document=True,
    )
    if not company:
        return jsonify({"error": "No account found for this email."}), 404

    otp_collection.delete_one({"_id": record["_id"]})

    token = create_access_token(identity=str(company["_id"]))

    return jsonify({
        "message": "Email verified successfully.",
        "token": token,
        "company_id": str(company["_id"]),
        "company_name": company["company_name"],
    }), 200


# ---------------------------------------------------------------------------
# POST /api/auth/resend-otp
# ---------------------------------------------------------------------------

@auth_bp.route("/resend-otp", methods=["POST"])
@limiter.limit("5 per hour")
def resend_otp():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()

    if not email:
        return jsonify({"error": "email is required."}), 400

    company = companies_collection.find_one({"email": email})
    if not company:
        return jsonify({"error": "No account found for this email."}), 404
    if company.get("is_verified"):
        return jsonify({"error": "This account is already verified."}), 400

    otp_collection.delete_many({"email": email})

    otp = generate_otp()
    otp_collection.insert_one({
        "email": email,
        "otp": otp,
        "company_id": str(company["_id"]),
        "expires_at": otp_expiry_timestamp(minutes=1),
    })

    try:
        _send_otp_email(email, company["company_name"], otp)
    except Exception as e:
        print(f"[auth/resend-otp] Email send failed: {e}")

    return jsonify({"message": "A new verification code has been sent."}), 200


# ---------------------------------------------------------------------------
# POST /api/auth/login
# ---------------------------------------------------------------------------

@auth_bp.route("/login", methods=["POST"])
@limiter.limit("10 per 15 minutes")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "email and password are required."}), 400

    company = companies_collection.find_one({"email": email})

    # Same error message for "no account" and "wrong password" on purpose
    # — avoids leaking which emails are registered.
    invalid_credentials = jsonify({"error": "Invalid email or password."}), 401

    if not company:
        return invalid_credentials
    if not verify_password(password, company["password"]):
        return invalid_credentials

    if not company.get("is_verified"):
        return jsonify({
            "error": "Please verify your email before logging in.",
            "email": email,
        }), 403

    token = create_access_token(identity=str(company["_id"]))

    return jsonify({
        "message": "Login successful.",
        "token": token,
        "company_id": str(company["_id"]),
        "company_name": company["company_name"],
    }), 200


# ---------------------------------------------------------------------------
# GET /api/auth/me — returns the logged-in company's own profile.
# Useful for the frontend to confirm a stored token is still valid and to
# populate the dashboard header without a separate lookup call.
# ---------------------------------------------------------------------------

@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    company = get_current_company()
    if not company:
        return jsonify({"error": "Company not found."}), 404
    company_doc = companies_collection.find_one({"_id": ObjectId(company["company_id"])})
    if not company_doc:
        return jsonify({"error": "Company not found."}), 404

    return jsonify({
        "company_id": str(company_doc["_id"]),
        "email": company_doc.get("email"),
        "company_name": company_doc.get("company_name"),
        "full_name": company_doc.get("full_name"),
        "company_logo_url": company_doc.get("company_logo_url"),
        "is_verified": company_doc.get("is_verified", False),
    }), 200


@auth_bp.route("/me", methods=["PATCH"])
@jwt_required()
def update_me():
    company = get_current_company()
    if not company:
        return jsonify({"error": "Company not found."}), 404

    body = request.get_json(silent=True) or {}
    company_name = (body.get("company_name") or "").strip()
    full_name = (body.get("full_name") or "").strip()
    logo_value = body.get("company_logo_url")

    update_fields = {}
    if company_name:
        update_fields["company_name"] = company_name
    if full_name:
        update_fields["full_name"] = full_name
    if "company_logo_url" in body:
        update_fields["company_logo_url"] = (logo_value or "").strip() or None

    if not update_fields:
        return jsonify({"error": "Provide at least one profile field to update."}), 400

    companies_collection.update_one(
        {"_id": ObjectId(company["company_id"])},
        {"$set": update_fields},
    )

    company_doc = companies_collection.find_one({"_id": ObjectId(company["company_id"])})
    if not company_doc:
        return jsonify({"error": "Company not found."}), 404

    return jsonify({
        "message": "Profile updated successfully.",
        "company": {
            "company_id": str(company_doc["_id"]),
            "email": company_doc.get("email"),
            "company_name": company_doc.get("company_name"),
            "full_name": company_doc.get("full_name"),
            "company_logo_url": company_doc.get("company_logo_url"),
            "is_verified": company_doc.get("is_verified", False),
        }
    }), 200


# ---------------------------------------------------------------------------
# POST /api/auth/forgot-password
# Sends a password reset link (signed token, 1h expiry) to the company's
# email. Always returns 200 — never reveals whether the email is registered.
# ---------------------------------------------------------------------------

@auth_bp.route("/forgot-password", methods=["POST"])
@limiter.limit("5 per hour")
def forgot_password():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()

    if not email:
        return jsonify({"error": "email is required."}), 400

    from utils.token_utils import generate_password_reset_token
    from config import Config

    generic_ok = jsonify({
        "message": "If that email is registered, a password reset link has been sent."
    }), 200

    company = companies_collection.find_one({"email": email})
    if not company:
        return generic_ok  # don't leak which emails exist

    token = generate_password_reset_token(company_id=str(company["_id"]))

    reset_url = f"{Config.FRONTEND_URL.rstrip('/')}/reset-password?token={token}"
    subject = "Reset your AuraX AI password"
    body = (
        f"Hi {company.get('full_name') or company.get('company_name')},\n\n"
        f"We received a request to reset your AuraX AI password.\n\n"
        f"Open this link to choose a new password (valid for 1 hour):\n"
        f"{reset_url}\n\n"
        f"If you didn't request this, you can safely ignore this email — "
        f"your password will not change.\n\n"
        f"— AuraX AI"
    )

    try:
        send_email(to_email=email, subject=subject, body=body, from_name="AuraX AI")
    except Exception as e:
        print(f"[auth/forgot-password] Email send failed: {e}")

    return generic_ok


# ---------------------------------------------------------------------------
# POST /api/auth/reset-password
# Consumes the signed reset token and sets the new password.
# ---------------------------------------------------------------------------

@auth_bp.route("/reset-password", methods=["POST"])
@limiter.limit("10 per hour")
def reset_password():
    data = request.get_json(silent=True) or {}
    token = (data.get("token") or "").strip()
    new_password = data.get("new_password") or ""

    if not token or not new_password:
        return jsonify({"error": "token and new_password are required."}), 400
    if len(new_password) < 8:
        return jsonify({"error": "Password must be at least 8 characters."}), 400

    from utils.token_utils import verify_password_reset_token

    try:
        payload = verify_password_reset_token(token)
    except Exception:
        return jsonify({"error": "Invalid or expired reset link. Please request a new one."}), 400

    company_id = payload.get("company_id")
    if not company_id:
        return jsonify({"error": "Invalid reset token."}), 400

    try:
        oid = ObjectId(company_id)
    except Exception:
        return jsonify({"error": "Invalid reset token."}), 400

    result = companies_collection.update_one(
        {"_id": oid},
        {"$set": {
            "password": hash_password(new_password),
            "updated_at": datetime.now(timezone.utc),
        }},
    )
    if result.matched_count == 0:
        return jsonify({"error": "Account not found."}), 404

    return jsonify({"message": "Password reset successfully. You can now log in."}), 200
