"""
create_user.py — create (or reset) a verified company account directly in the DB.

Usage:
    python create_user.py                                # uses the defaults below
    python create_user.py email password "Company" "Full Name"

The account is created with is_verified=True (no OTP email needed).
"""

import sys
import os
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils.db import companies_collection
from utils.auth_helpers import hash_password


def create_credentials():
    # Defaults (used when no CLI args are given)
    email = "chakradharreddy814@gmail.com"
    password = "CHAKRI@799"
    company_name = "AuraX AI"
    full_name = "Chakradhar Reddy"

    if len(sys.argv) >= 3:
        email = sys.argv[1].strip().lower()
        password = sys.argv[2]
        company_name = sys.argv[3] if len(sys.argv) >= 4 else "AuraX AI"
        full_name = sys.argv[4] if len(sys.argv) >= 5 else email.split("@")[0]

    print(f"Creating/updating credentials for {email}...")
    existing = companies_collection.find_one({"email": email})

    if existing:
        print("Account already exists. Updating password and verifying...")
        companies_collection.update_one(
            {"_id": existing["_id"]},
            {
                "$set": {
                    "password": hash_password(password),
                    "is_verified": True,
                    "company_name": company_name,
                    "full_name": full_name,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        print("Credentials updated successfully!")
    else:
        print("Creating new verified company account...")
        company_doc = {
            "email": email,
            "password": hash_password(password),
            "company_name": company_name,
            "full_name": full_name,
            "is_verified": True,
            "company_logo_url": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        companies_collection.insert_one(company_doc)
        print("Credentials created successfully!")


if __name__ == "__main__":
    create_credentials()
