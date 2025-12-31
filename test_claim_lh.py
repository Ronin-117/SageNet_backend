import requests
import json

# ================= CONFIGURATION =================
FIREBASE_API_KEY = "AIzaSyD1a_bQy_1Etv8qCV-PmLOX-9InW2wDZ1Y" # Your Real Key
USER_EMAIL = "njytc002@gmail.com" 
USER_PASS  = "password123"    

BASE_URL  = "https://sagenet-energy.duckdns.org"
DEVICE_ID = "esp32_d4ea33dd2568" # Your Real Device ID

# ================= LOGIC =================

def login():
    """Login to Firebase to get JWT Token"""
    print(f"🔐 Logging in as {USER_EMAIL}...")
    auth_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    res = requests.post(auth_url, json={"email": USER_EMAIL, "password": USER_PASS, "returnSecureToken": True})
    
    if res.status_code == 200:
        token = res.json()['idToken']
        print(f"✅ Login Success!")
        return token
    else:
        print("❌ Login Failed:", res.text)
        exit()

def test_claim_device(token):
    """TEST 1: Claiming a Device (Linking User -> Device)"""
    print(f"\n🔗 Attempting to Claim Device {DEVICE_ID}...")
    
    url = f"{BASE_URL}/api/v1/devices/claim"
    headers = {"Authorization": f"Bearer {token}"}
    
    payload = {
        "device_id": DEVICE_ID,
        "friendly_name": "Test Python Switch"
    }
    
    try:
        res = requests.post(url, json=payload, headers=headers)
        if res.status_code == 200:
            print("✅ SUCCESS: Device Claimed!")
            print("   -> Check Firestore 'devices' collection to confirm owner_id.")
        else:
            print(f"❌ FAILED: {res.status_code} - {res.text}")
    except Exception as e:
        print("Error:", e)

def test_daily_history(token):
    """TEST 2: Fetching Long-Term History (Daily Averages)"""
    print(f"\n📅 Fetching Last 7 Days History...")
    
    # Query param: ?days=7
    url = f"{BASE_URL}/api/v1/devices/{DEVICE_ID}/history/daily?days=7"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            data = res.json()
            print("✅ SUCCESS: Retrieved Daily Stats")
            print(json.dumps(data, indent=2)) # Pretty print JSON
        else:
            print(f"❌ FAILED: {res.status_code} - {res.text}")
    except Exception as e:
        print("Error:", e)

def test_control(token):
    """TEST 3: Toggle Relay"""
    print(f"\n🚀 Toggling Relay...")
    url = f"{BASE_URL}/api/v1/devices/{DEVICE_ID}/control"
    headers = {"Authorization": f"Bearer {token}"}
    
    # Toggle ON
    requests.post(url, json={"index": 0, "state": True}, headers=headers)
    print("✅ Command Sent")

if __name__ == "__main__":
    # 1. Login
    jwt = login()
    
    # 2. Run Tests
    test_claim_device(jwt)
    test_control(jwt)
    test_daily_history(jwt)