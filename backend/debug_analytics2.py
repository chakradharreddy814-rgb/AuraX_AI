"""Test analytics endpoint logic directly."""
from utils.db import candidates_collection, jobs_collection, pipeline_collection
from utils.auth_helper import get_current_company
from bson import ObjectId

# Simulate the company_id we get from auth
company_id = "6a59bc043a49b2ec051f8735"
print(f"Using company_id: '{company_id}' (type: {type(company_id).__name__})")

# Test the find query
all_candidates = list(candidates_collection.find({"company_id": company_id}))
print(f"\nCandidates found with company_id filter: {len(all_candidates)}")
for c in all_candidates:
    job_id = c.get("job_id", "")
    print(f"  {c.get('candidate_name')} | job_id: {job_id}")
    
    # Test job lookup
    try:
        job = jobs_collection.find_one({"_id": ObjectId(job_id)})
        if job:
            title = job.get("title") or job.get("job_title")
            print(f"    -> job found: '{title}'")
        else:
            print(f"    -> job NOT found by ObjectId")
            # Try string match
            job2 = jobs_collection.find_one({"_id": job_id})
            print(f"    -> job by string _id: {job2}")
    except Exception as e:
        print(f"    -> exception: {e}")
