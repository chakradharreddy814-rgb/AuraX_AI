from utils.db import candidates_collection
from bson import ObjectId

# Update Gnanesh's email to the verified gmail address
result = candidates_collection.update_one(
    {'_id': ObjectId('6a5a018233774cd1fc27d6ac')},
    {'$set': {'candidate_email': 'chakradharreddy814@gmail.com', 'status': 'screened'}}
)
print(f'Modified: {result.modified_count}')

# Verify
c = candidates_collection.find_one({'_id': ObjectId('6a5a018233774cd1fc27d6ac')})
if c:
    print(f'Candidate: {c["candidate_name"]} -> {c["candidate_email"]}')
    print(f'Status: {c["status"]}')
else:
    print('Not found by that ID, searching all screened candidates...')
    screened = list(candidates_collection.find({'status': 'screened'}))
    for s in screened:
        print(f"  ID: {s['_id']} | {s['candidate_name']} | {s.get('candidate_email','no email')}")
