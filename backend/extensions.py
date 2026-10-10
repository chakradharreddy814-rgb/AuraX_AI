"""
extensions.py — Shared Flask extensions, created here (uninitialized) so
that blueprints can import them without a circular import with app.py.
app.py calls limiter.init_app(app) after creating the Flask app.
"""

import os
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Rate limiting — protects login/OTP/public endpoints from brute force.
# Backed by in-memory storage (fine for a single-process deploy; set
# RATELIMIT_STORAGE_URI to a Redis URL when running multiple workers).
limiter = Limiter(
    get_remote_address,
    default_limits=["200 per hour"],
    storage_uri=os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
)
