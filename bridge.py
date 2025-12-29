import os
import json
import time
import ssl
from dotenv import load_dotenv
import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
import firebase_admin
from firebase_admin import credentials, firestore

# 1. Load Config
load_dotenv()

# 2. Initialize Firebase (Identity Manager)
cred = credentials.Certificate(os.getenv("FIREBASE_CRED"))
firebase_admin.initialize_app(cred)
db = firestore.client()
print("✅ Firebase Initialized")

# 3. Initialize InfluxDB (Data Lake)
influx_client = InfluxDBClient(
    url=os.getenv("INFLUX_URL"),
    token=os.getenv("INFLUX_TOKEN"),
    org=os.getenv("INFLUX_ORG")
)
write_api = influx_client.write_api(write_options=SYNCHRONOUS)
print("✅ InfluxDB Initialized")

# Cache to store Owner IDs (Prevent spamming Firebase)
device_cache = {}

# ================= LOGIC =================

def get_device_owner(device_id):
    """Checks cache first, then DB."""
    if device_id in device_cache:
        return device_cache[device_id]
    
    print(f"🔍 Looking up owner for {device_id}...")
    doc = db.collection('devices').document(device_id).get()
    
    if doc.exists:
        owner_id = doc.to_dict().get('owner_id')
        device_cache[device_id] = owner_id
        print(f"👤 Found Owner: {owner_id}")
        return owner_id
    else:
        print(f"⚠️ Unknown Device {device_id}. Ignoring.")
        return None

def on_connect(client, userdata, flags, rc, properties=None): # Updated signature for MQTT v5
    print(f"✅ Connected to HiveMQ (RC: {rc})")
    client.subscribe("evt/+/telem")

def on_message(client, userdata, msg):
    try:
        # Topic: evt/{device_id}/telem
        topic_parts = msg.topic.split('/')
        device_id = topic_parts[1]
        
        payload = json.loads(msg.payload.decode())
        print(f"[{device_id}] Data received")

        # 1. Enrich (Find Owner)
        owner_id = get_device_owner(device_id)
        if not owner_id:
            return

        # 2. Transform for InfluxDB
        # Structure: Measurement, Tags, Fields
        point = Point("energy_usage") \
            .tag("device_id", device_id) \
            .tag("owner_id", owner_id) \
            .field("voltage", float(payload.get('v', 0)))

        # Handle Arrays (Currents & States)
        # payload['c'] = [1.2, 0.5, ...]
        currents = payload.get('c', [])
        for i, val in enumerate(currents):
            point.field(f"current_{i}", float(val))
            point.field(f"power_{i}", float(val) * float(payload.get('v', 0)))

        states = payload.get('s', [])
        for i, val in enumerate(states):
            point.field(f"state_{i}", int(val))

        # 3. Write to Influx
        write_api.write(bucket=os.getenv("INFLUX_BUCKET"), record=point)
        print("💾 Saved to InfluxDB")

    except Exception as e:
        print(f"❌ Error: {e}")

# ================= MQTT SETUP =================

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="python_bridge_v1")
client.username_pw_set(os.getenv("MQTT_USER"), os.getenv("MQTT_PASS"))

# SSL/TLS is REQUIRED for HiveMQ Cloud
client.tls_set(cert_reqs=ssl.CERT_NONE) 
client.tls_insecure_set(True)

client.on_connect = on_connect
client.on_message = on_message

print("⏳ Connecting to HiveMQ...")
client.connect(os.getenv("MQTT_BROKER"), int(os.getenv("MQTT_PORT")), 60)

# Blocking loop (This script runs forever)
client.loop_forever()