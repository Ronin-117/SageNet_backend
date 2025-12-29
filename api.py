import os
import json
import ssl
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient
import firebase_admin
from firebase_admin import credentials, firestore

# 1. Load Config
load_dotenv()

# 2. Initialize FastAPI
app = FastAPI(title="Smart Energy API", version="1.0")

# 3. Initialize Firebase (Check if already initialized to avoid errors)
if not firebase_admin._apps:
    cred = credentials.Certificate(os.getenv("FIREBASE_CRED"))
    firebase_admin.initialize_app(cred)
db = firestore.client()

# 4. Initialize MQTT (Publisher Only)
mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="fastapi_publisher")
mqtt_client.username_pw_set(os.getenv("MQTT_USER"), os.getenv("MQTT_PASS"))
mqtt_client.tls_set(cert_reqs=ssl.CERT_NONE)
mqtt_client.tls_insecure_set(True)

print("⏳ API Connecting to HiveMQ...")
mqtt_client.connect(os.getenv("MQTT_BROKER"), int(os.getenv("MQTT_PORT")), 60)
mqtt_client.loop_start() # Run in background

# 5. Initialize InfluxDB (Reader)
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

# --- ENDPOINTS ---

@app.get("/")
def read_root():
    return {"status": "online", "service": "Smart Energy API"}

@app.post("/devices/{device_id}/control")
def control_device(device_id: str, cmd: RelayCommand, uid: str = Header(None)):
    """
    Turns a relay ON/OFF.
    Header 'uid' simulates the User ID coming from the App.
    """
    if not uid:
        raise HTTPException(status_code=401, detail="Missing User ID")

    # 1. Security Check: Does this user own this device?
    # (In production, we cache this. For now, we query DB).
    doc = db.collection('devices').document(device_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if doc.to_dict().get('owner_id') != uid:
        raise HTTPException(status_code=403, detail="You do not own this device")

    # 2. Construct Command Topic & Payload
    # Topic: cmd/{device_id}/set
    # Payload: {"i": 0, "s": true}
    topic = f"cmd/{device_id}/set"
    payload = json.dumps({"i": cmd.index, "s": cmd.state})

    # 3. Publish to MQTT
    info = mqtt_client.publish(topic, payload, qos=1)
    
    if info.rc != mqtt.MQTT_ERR_SUCCESS:
        raise HTTPException(status_code=500, detail="MQTT Publish Failed")

    return {"status": "success", "action": "published", "device": device_id}

@app.get("/devices/{device_id}/history")
def get_device_history(device_id: str):
    """
    Fetches the last 10 voltage readings from InfluxDB.
    """
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