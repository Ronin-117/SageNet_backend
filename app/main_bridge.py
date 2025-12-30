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
        client.subscribe("evt/+/telem")
    else:
        log.error(f"Connection Failed. RC: {rc}")

def on_message(client, userdata, msg):
    try:
        topic_parts = msg.topic.split('/')
        device_id = topic_parts[1]
        payload = json.loads(msg.payload.decode())

        # Enrichment
        owner_id = owner_cache.get(device_id)
        if not owner_id:
            owner_id = firebase_svc.get_device_owner(device_id)
            if owner_id:
                owner_cache[device_id] = owner_id
            else:
                log.warning(f"Unknown Device: {device_id}")
                return

        # Storage
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