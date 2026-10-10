import sys
import os
from pymongo import MongoClient, ASCENDING
from bson import ObjectId
import json
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import Config

class LocalCollection:
    def __init__(self, db_path, collection_name):
        self.db_path = db_path
        self.collection_name = collection_name

    def _load_data(self):
        if not os.path.exists(self.db_path):
            return {}
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_data(self, data):
        try:
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            print(f"[LocalDB] Error saving data: {e}")

    def create_index(self, keys, unique=False):
        pass

    def insert_one(self, document):
        data = self._load_data()
        if self.collection_name not in data:
            data[self.collection_name] = []
        
        doc_copy = dict(document)
        if "_id" not in doc_copy:
            doc_copy["_id"] = str(ObjectId())
        else:
            doc_copy["_id"] = str(doc_copy["_id"])
            
        data[self.collection_name].append(doc_copy)
        self._save_data(data)
        
        class InsertResult:
            def __init__(self, inserted_id):
                self.inserted_id = inserted_id
        return InsertResult(ObjectId(doc_copy["_id"]))

    def _match(self, doc, query):
        if not query:
            return True
        for k, v in query.items():
            doc_val = doc.get(k)
            if k == "_id":
                if str(doc_val) != str(v):
                    return False
            elif isinstance(v, dict):
                # Basic support for operators if any
                pass
            else:
                if doc_val != v:
                    return False
        return True

    def find_one(self, query=None):
        data = self._load_data()
        docs = data.get(self.collection_name, [])
        for doc in docs:
            if self._match(doc, query):
                res = dict(doc)
                res["_id"] = ObjectId(res["_id"])
                return res
        return None

    def find(self, query=None):
        data = self._load_data()
        docs = data.get(self.collection_name, [])
        matched = []
        for doc in docs:
            if self._match(doc, query):
                res = dict(doc)
                res["_id"] = ObjectId(res["_id"])
                matched.append(res)
        
        class Cursor:
            def __init__(self, items):
                self.items = items
            def __iter__(self):
                return iter(self.items)
            def sort(self, key, direction=1):
                reverse = (direction == -1)
                self.items.sort(key=lambda x: x.get(key) or "", reverse=reverse)
                return self
        return Cursor(matched)

    def update_one(self, query, update):
        data = self._load_data()
        docs = data.get(self.collection_name, [])
        updated = False
        for doc in docs:
            if self._match(doc, query):
                self._apply_update(doc, update)
                updated = True
                break
        if updated:
            self._save_data(data)
        class UpdateResult:
            def __init__(self, matched_count, modified_count):
                self.matched_count = matched_count
                self.modified_count = modified_count
        return UpdateResult(1 if updated else 0, 1 if updated else 0)

    def find_one_and_update(self, query, update, return_document=None):
        data = self._load_data()
        docs = data.get(self.collection_name, [])
        for doc in docs:
            if self._match(doc, query):
                original = dict(doc)
                original["_id"] = ObjectId(original["_id"])
                self._apply_update(doc, update)
                self._save_data(data)
                if return_document:
                    updated = dict(doc)
                    updated["_id"] = ObjectId(updated["_id"])
                    return updated
                return original
        return None

    def delete_one(self, query):
        data = self._load_data()
        docs = data.get(self.collection_name, [])
        deleted = False
        for i, doc in enumerate(docs):
            if self._match(doc, query):
                docs.pop(i)
                deleted = True
                break
        if deleted:
            self._save_data(data)
        class DeleteResult:
            def __init__(self, deleted_count):
                self.deleted_count = deleted_count
        return DeleteResult(1 if deleted else 0)

    def delete_many(self, query):
        data = self._load_data()
        docs = data.get(self.collection_name, [])
        initial_len = len(docs)
        new_docs = [doc for doc in docs if not self._match(doc, query)]
        deleted_count = initial_len - len(new_docs)
        if deleted_count > 0:
            data[self.collection_name] = new_docs
            self._save_data(data)
        class DeleteResult:
            def __init__(self, deleted_count):
                self.deleted_count = deleted_count
        return DeleteResult(deleted_count)

    def count_documents(self, query=None):
        """Count documents matching query (MongoDB compatibility)."""
        return len(list(self.find(query or {})))

    def aggregate(self, pipeline):
        """
        Simplified aggregate for local DB — handles the common patterns used in
        jobs.py and dashboard.py:
          1. [{$match: ...}, {$group: {_id: "$field", count: {$sum: 1}}}]
          2. [{$match: ...}, {$group: {_id: "$field", avg_score: {$avg: "$field"}}}]
          3. [{$match: ...}, {$group: {_id: None, avg_score: {$avg: "$field"}}}]
          4. [{$match: ...}, {$group: {_id: {job_id: "$job_id", status: "$status"}, count: {$sum: 1}}}]
        """
        pipeline = list(pipeline)
        # Extract $match and $group stages
        match_query = {}
        group_spec = {}
        for stage in pipeline:
            if "$match" in stage:
                match_query = stage["$match"]
            elif "$group" in stage:
                group_spec = stage["$group"]

        docs = list(self.find(match_query))
        group_id_spec = group_spec.get("_id")

        # Determine aggregation type
        has_sum = any("$sum" in str(v) for k, v in group_spec.items() if k != "_id")
        has_avg = any(isinstance(v, dict) and "$avg" in v for k, v in group_spec.items() if k != "_id")

        # Compound group key (e.g. {job_id: "$job_id", status: "$status"})
        if isinstance(group_id_spec, dict):
            groups = {}
            for doc in docs:
                key = tuple(
                    (k, doc.get(v.lstrip("$") if isinstance(v, str) and v.startswith("$") else v))
                    for k, v in group_id_spec.items()
                )
                if key not in groups:
                    groups[key] = 0
                groups[key] += 1
            return [
                {"_id": dict(key), "count": count}
                for key, count in groups.items()
            ]

        # Global aggregate (group_id_spec is None)
        if group_id_spec is None:
            if has_avg:
                avg_key = next(k for k in group_spec if k != "_id")
                avg_field = group_spec[avg_key]["$avg"].lstrip("$")
                scores = [doc.get(avg_field) for doc in docs if doc.get(avg_field) is not None]
                if scores:
                    return [{"_id": None, avg_key: sum(scores) / len(scores)}]
                return []
            if has_sum:
                total = sum(group_spec[k].get("$sum", 0) if isinstance(group_spec[k], dict) else 0
                            for k in group_spec if k != "_id")
                return [{"_id": None, "count": len(docs)}]
            return []

        # Group by a single field
        if isinstance(group_id_spec, str) and group_id_spec.startswith("$"):
            group_field = group_id_spec.lstrip("$")
            if has_avg:
                avg_key = next(k for k in group_spec if k != "_id")
                avg_field = group_spec[avg_key]["$avg"].lstrip("$")
                groups = {}
                for doc in docs:
                    key = doc.get(group_field)
                    if key not in groups:
                        groups[key] = []
                    score = doc.get(avg_field)
                    if score is not None:
                        groups[key].append(score)
                return [
                    {"_id": key, avg_key: sum(scores) / len(scores)}
                    for key, scores in groups.items() if scores
                ]
            if has_sum:
                groups = {}
                for doc in docs:
                    key = doc.get(group_field)
                    if key not in groups:
                        groups[key] = 0
                    groups[key] += 1
                return [{"_id": key, "count": count} for key, count in groups.items()]

        return []

    def _apply_update(self, doc, update):
        if "$set" in update:
            for k, v in update["$set"].items():
                if isinstance(v, datetime):
                    doc[k] = v.isoformat()
                else:
                    doc[k] = v
        if "$inc" in update:
            for k, v in update["$inc"].items():
                doc[k] = doc.get(k, 0) + v


class LocalDatabase:
    def __init__(self, db_path):
        self.db_path = db_path
        self._collections = {}

    def __getitem__(self, name):
        if name not in self._collections:
            self._collections[name] = LocalCollection(self.db_path, name)
        return self._collections[name]

    def list_collection_names(self):
        if not os.path.exists(self.db_path):
            return []
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return list(data.keys())
        except Exception:
            return []


# Initialize DB Connection
db = None
client = None
is_local_db = False

try:
    print("Connecting to MongoDB Atlas...")
    client = MongoClient(Config.MONGODB_URI, serverSelectionTimeoutMS=2000)
    # Ping to check if connection actually works (e.g. whitelisting, credentials check)
    client.admin.command("ping")
    db = client[Config.DB_NAME]
    print("Connected to MongoDB Atlas successfully!")
except Exception as e:
    print("Warning: MongoDB Atlas connection failed. Error:", str(e))
    print("Falling back to local file-based database...")
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "local_db.json")
    db = LocalDatabase(db_path)
    is_local_db = True

# Define collections
companies_collection = db["companies"]
jobs_collection = db["jobs"]
candidates_collection = db["candidates"]
pipeline_collection = db["pipeline"]
otp_collection = db["otps"]
password_reset_collection = db["password_resets"]  # audit trail of reset requests (tokens are self-contained, not stored secrets)

# Indexes (for Atlas or local mock)
try:
    companies_collection.create_index([("email", ASCENDING)], unique=True)
    jobs_collection.create_index([("company_id", ASCENDING)])
    candidates_collection.create_index([("company_id", ASCENDING)])
    candidates_collection.create_index([("job_id", ASCENDING)])
    otp_collection.create_index([("expires_at", ASCENDING)], expireAfterSeconds=0)
    password_reset_collection.create_index([("created_at", ASCENDING)], expireAfterSeconds=60*60*24*30)
except Exception:
    pass

if __name__ == "__main__":
    if is_local_db:
        print("Running with local database fallback.")
        print("Collections:", db.list_collection_names())
    else:
        print("Running with Atlas database.")