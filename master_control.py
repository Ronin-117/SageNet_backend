import requests
import json
import time

# ================= CONFIGURATION =================
# 1. Your Firebase Web API Key (From Console)
FIREBASE_API_KEY = "AIzaSyD1a_bQy_1Etv8qCV-PmLOX-9InW2wDZ1Y"

# 2. Your Login Details
USER_EMAIL = "njytc002@gmail.com" 
USER_PASS  = "password123"    

# 3. Target Device
# Note: Base URL is the domain. We append /api/v1 later.
BASE_URL  = "https://sagenet-energy.duckdns.org"
DEVICE_ID = "esp32_d4ea33dd2568"

# ================= LOGIC =================

def login():
    """Exchanges Email/Pass for a secure JWT Token via Google Identity"""
    print(f"🔐 Logging in as {USER_EMAIL}...")
    
    auth_url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_API_KEY}"
    
    payload = {
        "email": USER_EMAIL,
        "password": USER_PASS,
        "returnSecureToken": True
    }
    
    res = requests.post(auth_url, json=payload)
    
    if res.status_code == 200:
        token = res.json()['idToken']
        uid = res.json()['localId']
        print(f"✅ Login Success! UID: {uid}")
        return token
    else:
        print("❌ Login Failed:", res.text)
        exit()

def toggle_light(token, state):
    """Sends the control command via the V1 API"""
    target_state = "ON" if state else "OFF"
    print(f"\n🚀 Sending Command: Relay 0 -> {target_state}...")
    
    # NEW URL STRUCTURE: /api/v1/devices/...
    url = f"{BASE_URL}/api/v1/devices/{DEVICE_ID}/control"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "index": 0,
        "state": state
    }
    
    try:
        res = requests.post(url, json=payload, headers=headers)
        
        if res.status_code == 200:
            data = res.json()
            print(f"✅ SUCCESS: {data.get('action')}")
            print("   -> Check your physical device now!")
        else:
            print(f"❌ FAILED: {res.status_code} - {res.text}")
            
    except Exception as e:
        print("Network Error:", e)

def check_history(token):
    """Fetches recent energy data to prove Read Access"""
    print(f"\n📈 Fetching History for {DEVICE_ID}...")
    
    url = f"{BASE_URL}/api/v1/devices/{DEVICE_ID}/history"
    
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    try:
        res = requests.get(url, headers=headers)
        
        if res.status_code == 200:
            data = res.json()
            count = data.get('count', 0)
            print(f"✅ SUCCESS: Retrieved {count} data points from InfluxDB.")
            if count > 0:
                print(f"   Latest Point: {data['data'][0]}")
        else:
            print(f"❌ FAILED: {res.status_code} - {res.text}")
            
    except Exception as e:
        print("Network Error:", e)

if __name__ == "__main__":
    # 1. Get the Passport (Token)
    jwt_token = login()
    
    # 2. Turn ON the Light
    toggle_light(jwt_token, True)
    
    # 3. Wait 2 seconds and Turn OFF (Optional test)
    # time.sleep(2)
    # toggle_light(jwt_token, False)

    # 4. Check if we can read data
    check_history(jwt_token)