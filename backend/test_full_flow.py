import time
import requests
import sys

BASE_URL = "http://localhost:8000"
API_URL = f"{BASE_URL}/api"

def run_test():
    print("1. Registering new user...")
    email = f"test_{int(time.time())}@example.com"
    pwd = "password123"
    r = requests.post(f"{API_URL}/auth/register", json={"email": email, "password": pwd})
    if not r.ok:
        print("Registration failed:", r.text)
        sys.exit(1)
    
    print("2. Logging in...")
    r = requests.post(f"{API_URL}/auth/login", json={"email": email, "password": pwd})
    if not r.ok:
        print("Login failed:", r.text)
        sys.exit(1)
    
    token = r.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}
    
    print("3. Creating project (yesandnowheel.com)...")
    r = requests.post(f"{API_URL}/projects/", headers=headers, json={"name": "Test Site", "domain": "https://www.yesandnowheel.com", "target_keywords": ["zodiac"]})
    if not r.ok:
        print("Project creation failed:", r.text)
        sys.exit(1)
    
    project_id = r.json().get("id")
    print(f"Project created with ID: {project_id}")
    
    print("4. Starting Scan...")
    r = requests.post(f"{API_URL}/projects/{project_id}/scan/start", headers=headers)
    if not r.ok:
        print("Scan start failed:", r.text)
        sys.exit(1)
    
    print("5. Polling scan status...")
    while True:
        r = requests.get(f"{API_URL}/projects/{project_id}/scan/status", headers=headers)
        if not r.ok:
            print("Status fetch failed:", r.text)
            sys.exit(1)
        
        status_data = r.json()
        status = status_data.get("status")
        percent = status_data.get("percent")
        urls_found = status_data.get("urls_found")
        urls_processed = status_data.get("urls_processed")
        
        print(f"Status: {status} | Progress: {percent}% | Processed: {urls_processed}/{urls_found}")
        
        if status in ("complete", "failed", "error"):
            break
            
        time.sleep(2)
        
    print("6. Fetching extracted keywords...")
    r = requests.get(f"{API_URL}/projects/{project_id}/keywords?page=1&page_size=10", headers=headers)
    if not r.ok:
        print("Keywords fetch failed:", r.text)
        sys.exit(1)
        
    keywords_data = r.json()
    keywords = keywords_data.get("items", [])
    
    print(f"\n--- SUCCESS! Extracted {keywords_data.get('total')} keywords ---")
    for kw in keywords:
        print(f" - {kw.get('keyword')} (Volume: {kw.get('volume')}, KD: {kw.get('difficulty')})")

if __name__ == "__main__":
    run_test()
