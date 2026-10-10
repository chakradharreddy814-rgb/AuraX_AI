"""Test analytics API with real login."""
import requests

# Login first to get a real JWT
login_resp = requests.post(
    "http://127.0.0.1:5000/api/auth/login",
    json={"email": "chakradharreddy814@gmail.com", "password": "CHAKRI@799"}
)
print(f"Login status: {login_resp.status_code}")
login_data = login_resp.json()
print(f"Login data keys: {list(login_data.keys())}")

token = login_data.get("access_token") or login_data.get("token")
print(f"Token: {token[:30] if token else 'None'}...")

if token:
    resp = requests.get(
        "http://127.0.0.1:5000/api/dashboard/analytics",
        headers={"Authorization": f"Bearer {token}"}
    )
    print(f"\nAnalytics status: {resp.status_code}")
    data = resp.json()
    print(f"Response keys: {list(data.keys())}")
    print(f"candidates count: {len(data.get('candidates', []))}")
    print(f"avg_time_to_decision_days: {data.get('avg_time_to_decision_days')}")
    for c in data.get('candidates', []):
        print(f"  {c['candidate_name']} | {c['job_title']} | score={c['match_score']} | {c['status']}")
