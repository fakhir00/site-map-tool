import requests

API_URL = "http://127.0.0.1:8000/api"

# Login to get token
resp = requests.post(f"{API_URL}/auth/login", data={"username": "test@test.com", "password": "password"})
if not resp.ok:
    print("Login failed:", resp.text)
    # try test user
    resp = requests.post(f"{API_URL}/auth/login", data={"username": "user@example.com", "password": "password"})

if not resp.ok:
    print("Login failed again:", resp.text)
    exit(1)

token = resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# Get projects
resp = requests.get(f"{API_URL}/projects", headers=headers)
projects = resp.json()
if not projects:
    print("No projects found")
    exit(1)

project_id = projects[0]["id"]
print(f"Testing on project: {project_id}")

# 1. Test intent buttons (manual-generate)
print("\n--- Testing Intent Button (manual-generate) ---")
payload = {
    "main_keyword": "test keyword",
    "keyword_cluster": "INSTRUCTION: This is a Test.",
    "project_id": project_id
}
try:
    resp = requests.post(f"{API_URL}/projects/manual-generate", json=payload, headers=headers)
    print("Intent Button Response:", resp.status_code)
    print(resp.text[:500])
except Exception as e:
    print("Intent Button Exception:", e)

# 2. Test HubSpoke button
print("\n--- Testing HubSpoke Button ---")
try:
    resp = requests.post(f"{API_URL}/projects/{project_id}/keywords/hub-spoke", headers=headers)
    print("HubSpoke Button Response:", resp.status_code)
    print(resp.text[:500])
except Exception as e:
    print("HubSpoke Button Exception:", e)

