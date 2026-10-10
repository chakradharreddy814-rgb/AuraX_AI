"""Debug script to check why /api/dashboard/analytics returns 0 candidates."""
from utils.db import candidates_collection, jobs_collection, pipeline_collection
import json

print("=== All candidates in local DB ===")
all_candidates = list(candidates_collection.find({}))
print(f"Total candidates: {len(all_candidates)}")

for c in all_candidates:
    print(f"  ID: {c['_id']} | name: {c.get('candidate_name')} | company_id: {c.get('company_id')} | job_id: {c.get('job_id')} | status: {c.get('status')}")

print("\n=== All jobs in local DB ===")
all_jobs = list(jobs_collection.find({}))
print(f"Total jobs: {len(all_jobs)}")
for j in all_jobs:
    print(f"  ID: {j['_id']} | title: {j.get('title') or j.get('job_title')} | company_id: {j.get('company_id')}")

print("\n=== Unique company_ids in candidates ===")
cids = set(c.get('company_id') for c in all_candidates)
print(cids)

print("\n=== Unique company_ids in jobs ===")
jids = set(j.get('company_id') for j in all_jobs)
print(jids)
