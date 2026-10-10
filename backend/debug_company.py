from utils.db import companies_collection
print("=== All companies ===")
for c in list(companies_collection.find({})):
    print(f"  _id: {c['_id']} (type: {type(c['_id']).__name__}) | email: {c.get('email')} | name: {c.get('name') or c.get('company_name')}")
