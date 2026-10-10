import sys
import os
from pymongo import MongoClient

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import Config

print("Testing MongoDB URI:", Config.MONGODB_URI)
try:
    # Use serverSelectionTimeoutMS=5000 so it fails fast if there is a connection issue
    client = MongoClient(Config.MONGODB_URI, serverSelectionTimeoutMS=5000)
    print("MongoClient created. Pinging...")
    client.admin.command("ping")
    print("MongoDB connected successfully!")
    db = client[Config.DB_NAME]
    print("Collections:", db.list_collection_names())
except Exception as e:
    print("Connection failed details:", str(e))
