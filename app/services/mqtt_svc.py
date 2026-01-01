import ssl
import json
import paho.mqtt.client as mqtt
from app.core.config import settings
from app.core.logger import setup_logger
import uuid

log = setup_logger("MqttService")

class MqttService:
    def __init__(self):
        # Generate a random ID every time (e.g., "fastapi_publisher_a1b2c3d4")
        random_suffix = str(uuid.uuid4())[:8]
        client_id = f"fastapi_publisher_{random_suffix}"
        
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        self.client.username_pw_set(settings.MQTT_USER, settings.MQTT_PASS)
        
        # SSL Config
        self.client.tls_set(cert_reqs=ssl.CERT_NONE)
        self.client.tls_insecure_set(True)
        
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect

    def on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            log.info("API connected to HiveMQ Broker")
        else:
            log.error(f"API MQTT Connection failed. RC: {rc}")

    def on_disconnect(self, client, userdata, flags, rc, properties=None):
        log.warning("API Disconnected from MQTT. Attempting auto-reconnect...")

    def start(self):
        try:
            log.info("Connecting API to MQTT...")
            self.client.connect(settings.MQTT_BROKER, settings.MQTT_PORT, 60)
            self.client.loop_start() # Run in background thread
        except Exception as e:
            log.error(f"Failed to start MQTT: {e}")

    def publish_command(self, device_id: str, index: int, state: bool):
        topic = f"cmd/{device_id}/set"
        payload = json.dumps({"i": index, "s": state})
        
        try:
            info = self.client.publish(topic, payload, qos=1,retain=False)
            info.wait_for_publish(timeout=2.0) # Wait up to 2s for ack
            
            if info.rc == mqtt.MQTT_ERR_SUCCESS:
                log.info(f"Command sent to {device_id}: Relay {index} -> {state}")
                return True
            else:
                log.error(f"MQTT Publish Error: {info.rc}")
                return False
        except Exception as e:
            log.error(f"Publish Exception: {e}")
            return False

mqtt_svc = MqttService()