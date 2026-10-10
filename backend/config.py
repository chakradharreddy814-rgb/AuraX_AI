"""
config.py — Centralized environment variable access.
Every other file reads secrets/settings through Config, instead of
calling os.getenv() everywhere.
"""

import os
from dotenv import load_dotenv

# Load env file from the same directory as config.py
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(dotenv_path=env_path)

class Config:
    MONGODB_URI = os.getenv("MONGODB_URI")
    DB_NAME = os.getenv("MONGODB_DB_NAME", "aurax")

    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash")

    RESEND_API_KEY = os.getenv("RESEND_API_KEY")
    RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL")
    
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

    if not MONGODB_URI:
        raise EnvironmentError("MONGODB_URI is not set in .env")
    if not GEMINI_API_KEY:
        raise EnvironmentError("GEMINI_API_KEY is not set in .env")