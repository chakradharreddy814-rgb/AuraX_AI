import sys
from pymongo import MongoClient

print("Testing Local MongoDB connection...")
try:
    client = MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=2000)
    client.admin.command("ping")
    print("Local MongoDB connected successfully!")
except Exception as e:
    print("Local MongoDB connection failed:", str(e))
