"""
utils/auth_helper.py — Authentication and JWT Helper Utilities.
Defines helpers to fetch and validate tenant/company credentials.

Note: `auth_helpers.py` (with an S) is the password/OTP crypto module;
this file is the JWT identity helper. They were consolidated here after
originally living under two confusable names — auth_helpers.py keeps the
password hashing + OTP functions, and this module keeps get_current_company.
"""

from flask_jwt_extended import get_jwt_identity
from utils.db import companies_collection
from bson import ObjectId

def get_current_company() -> dict:
    """
    Retrieves the current authenticated company's ID and name from the active JWT session.
    Tolerates various payload formats and queries the DB to map identity where needed.
    """
    identity = get_jwt_identity()
    if not identity:
        # Fallback for development/unauthenticated paths to prevent server crash
        return {
            "company_id": "default_company_id",
            "company_name": "Default Company"
        }
    
    # 1. Check if identity is already a dictionary containing ID and name
    if isinstance(identity, dict):
        company_id = identity.get("company_id") or identity.get("_id") or identity.get("id")
        company_name = identity.get("company_name") or identity.get("name")
        if company_id and company_name:
            return {"company_id": str(company_id), "company_name": str(company_name)}

    # 2. Try to query MongoDB companies collection using identity as ID or email
    try:
        search_query = {}
        if isinstance(identity, dict):
            if "email" in identity:
                search_query = {"email": identity["email"]}
            elif "_id" in identity:
                search_query = {"_id": ObjectId(identity["_id"])}
            elif "id" in identity:
                search_query = {"_id": ObjectId(identity["id"])}
        else:
            # String checks
            identity_str = str(identity)
            if len(identity_str) == 24 and all(c in "0123456789abcdefABCDEF" for c in identity_str):
                search_query = {"_id": ObjectId(identity_str)}
            else:
                search_query = {"email": identity_str}
        
        if search_query:
            company_doc = companies_collection.find_one(search_query)
            if company_doc:
                return {
                    "company_id": str(company_doc["_id"]),
                    "company_name": company_doc.get("name") or company_doc.get("company_name") or "Default Company"
                }
    except Exception as e:
        # Silently absorb DB or parsing issues and fallback
        print(f"[auth_helper] DB lookup failed: {e}")
        
    # 3. Fallback: return identity representation
    company_id = identity.get("company_id") if isinstance(identity, dict) else str(identity)
    company_name = identity.get("company_name") if isinstance(identity, dict) else "Default Company"
    return {
        "company_id": str(company_id) if company_id else "default_company_id",
        "company_name": str(company_name) if company_name else "Default Company"
    }
