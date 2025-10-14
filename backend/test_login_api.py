import requests
import json

# Test the login API endpoint
url = "http://localhost:8000/api/auth/login"
payload = {
    "username": "admin",
    "password": "admin123"
}

print(f"Testing login API at: {url}")
print(f"Payload: {json.dumps(payload, indent=2)}")
print("\nSending request...")

try:
    response = requests.post(url, json=payload)
    print(f"\nStatus Code: {response.status_code}")
    print(f"Response Headers: {dict(response.headers)}")
    print(f"Response Body: {response.text}")
    
    if response.status_code == 200:
        print("\n✓ Login successful!")
        data = response.json()
        print(f"Access Token: {data.get('access_token', 'N/A')[:50]}...")
    else:
        print(f"\n✗ Login failed!")
        
except Exception as e:
    print(f"\n✗ Error: {e}")

