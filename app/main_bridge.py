import time
import json
import ssl
import paho.mqtt.client as mqtt
from app.core.config import settings
from app.core.logger import setup_logger
from app.services.firebase_svc import firebase_svc
from app.services.influx_svc import influx_svc

log = setup_logger("MQTT_Bridge")

# Cache to reduce DB calls
owner_cache = {}

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        log.info("Connected to HiveMQ Broker")
        # 1. Listen for Direct Telemetry (Gateways)
        client.subscribe("evt/+/telem")
        # 2. Listen for Proxy Telemetry (Satellites via Gateway)
        client.subscribe("evt/+/proxy")
        # 3. Listen for Discovery Messages (New Devices)
        client.subscribe("evt/+/hive/discovery") 
    else:
        log.error(f"Connection Failed. RC: {rc}")

def on_message(client, userdata, msg):
    try:
        # Topic format: evt/{gateway_id}/{type}
        topic_parts = msg.topic.split('/')
        topic_id = topic_parts[1]
        msg_type = topic_parts[2] # 'telem' or 'proxy'

        if len(topic_parts) > 3: msg_type = topic_parts[3] # 'hive/discovery'
        
        payload = json.loads(msg.payload.decode())

        # --- CASE 0: ORPHAN DISCOVERY ---
        if msg_type == "discovery":
            # Payload: {"mac": "80:F3...", "rssi": -60, "type": "switch"}
            firebase_svc.save_discovered_orphan(topic_id, payload)
            return

        # --- STEP 1: IDENTIFY REAL DEVICE ---
        device_id = topic_id # Default to the sender (Gateway)

        if msg_type == "proxy":
            # If this is a proxy message, the REAL device ID is inside the JSON
            if 'real_device' in payload:
                device_id = payload['real_device']
                # Optional: Log occasionally to verify mesh works
                # log.info(f"Received Mesh Data for {device_id} via {topic_id}")
            else:
                log.warning(f"Proxy message from {topic_id} missing 'real_device' field.")
                return

        # --- STEP 2: ENRICHMENT (Owner Lookup) ---
        owner_id = owner_cache.get(device_id)
        if not owner_id:
            # Look up the OWNER of the REAL DEVICE (Satellite or Gateway)
            owner_id = firebase_svc.get_device_owner(device_id)
            if owner_id:
                owner_cache[device_id] = owner_id
            else:
                log.warning(f"Unknown Device: {device_id}")
                return
        
        # --- STEP 3: SYNC STATE (For Mobile App UI) ---
        if 's' in payload:
            # payload['s'] is [1, 0, 1, 0]
            # This updates the green/grey buttons in the app immediately
            firebase_svc.update_device_state(device_id, payload['s'])

        # --- STEP 4: STORAGE (InfluxDB) ---
        # Write data to the bucket for Graphs and AI
        influx_svc.write_telemetry(device_id, owner_id, payload)

    except Exception as e:
        log.error(f"Message Processing Error: {e}")

def run_bridge():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(settings.MQTT_USER, settings.MQTT_PASS)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.tls_insecure_set(True)
    client.on_connect = on_connect
    client.on_message = on_message

    while True:
        try:
            log.info("Connecting to MQTT...")
            client.connect(settings.MQTT_BROKER, settings.MQTT_PORT, 60)
            client.loop_forever()
        except Exception as e:
            log.critical(f"Bridge Crashed: {e}. Restarting in 5s...")
            time.sleep(5)

if __name__ == "__main__":
    run_bridge()