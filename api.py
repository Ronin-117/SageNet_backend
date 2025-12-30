import os
import json
import ssl
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient
import firebase_admin
from firebase_admin import credentials, firestore, auth

# 1. Load Config
load_dotenv()

# 2. Initialize FastAPI
app = FastAPI(title="Smart Energy API", version="2.0 (Secure)")
security = HTTPBearer()

# 3. Initialize Firebase
if not firebase_admin._apps:
    cred = credentials.Certificate(os.getenv("FIREBASE_CRED"))
    firebase_admin.initialize_app(cred)
db = firestore.client()

# 4. Initialize MQTT (Publisher)
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="fastapi_publisher")
mqtt_client.username_pw_set(os.getenv("MQTT_USER"), os.getenv("MQTT_PASS"))
mqtt_client.tls_set(cert_reqs=ssl.CERT_NONE)
mqtt_client.tls_insecure_set(True)

print("⏳ API Connecting to HiveMQ...")
mqtt_client.connect(os.getenv("MQTT_BROKER"), int(os.getenv("MQTT_PORT")), 60)
mqtt_client.loop_start()

# 5. InfluxDB (Reader)
influx_client = InfluxDBClient(
    url=os.getenv("INFLUX_URL"),
    token=os.getenv("INFLUX_TOKEN"),
    org=os.getenv("INFLUX_ORG")
)
query_api = influx_client.query_api()

# --- DATA MODELS ---
class RelayCommand(BaseModel):
    index: int
    state: bool

# --- SECURITY DEPENDENCY ---
def get_current_user(creds: HTTPAuthorizationCredentials = Security(security)):
    """
    Validates the Firebase JWT Token sent by the App.
    Returns the User ID (uid) if valid, else raises 401.
    """
    token = creds.credentials
    try:
        # Verify the token against Google's servers
        decoded_token = auth.verify_id_token(token)
        uid = decoded_token['uid']
        return uid
    except Exception as e:
        print(f"Auth Error: {e}")
        raise HTTPException(status_code=401, detail="Invalid or Expired Token")

# --- ENDPOINTS ---

@app.get("/")
def read_root():
    return {"status": "online", "security": "JWT Enabled"}

@app.post("/devices/{device_id}/control")
def control_device(
    device_id: str, 
    cmd: RelayCommand, 
    uid: str = Depends(get_current_user) # <--- AUTOMATIC SECURITY CHECK
):
    """
    Only runs if the Token is valid. 'uid' is extracted securely.
    """
    # 1. Ownership Check
    doc = db.collection('devices').document(device_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if doc.to_dict().get('owner_id') != uid:
        raise HTTPException(status_code=403, detail="You do not own this device")

    # 2. Publish Command
    topic = f"cmd/{device_id}/set"
    payload = json.dumps({"i": cmd.index, "s": cmd.state})

    info = mqtt_client.publish(topic, payload, qos=1)
    
    if info.rc != mqtt.MQTT_ERR_SUCCESS:
        raise HTTPException(status_code=500, detail="MQTT Publish Failed")

    return {"status": "success", "action": "published", "device": device_id}

@app.get("/devices/{device_id}/history")
def get_device_history(device_id: str, uid: str = Depends(get_current_user)):
    """
    Securely fetch history.
    """
    # 1. Ownership Check
    doc = db.collection('devices').document(device_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if doc.to_dict().get('owner_id') != uid:
        raise HTTPException(status_code=403, detail="Access Denied")

    # 2. Query Influx
    bucket = os.getenv("INFLUX_BUCKET")
    query = f'''
    from(bucket: "{bucket}")
      |> range(start: -1h)
      |> filter(fn: (r) => r["_measurement"] == "energy_usage")
      |> filter(fn: (r) => r["device_id"] == "{device_id}")
      |> filter(fn: (r) => r["_field"] == "voltage")
      |> limit(n: 10)
    '''
    try:
        result = query_api.query(org=os.getenv("INFLUX_ORG"), query=query)
        data = []
        for table in result:
            for record in table.records:
                data.append({"time": record.get_time(), "voltage": record.get_value()})
        return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))