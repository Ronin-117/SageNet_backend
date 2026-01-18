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
        # 1. Check if this is a Satellite
        # We need to look up the device in Firestore to see if it has a 'parent_gateway'
        from app.services.firebase_svc import firebase_svc # Import inside method to avoid circular import
        
        device_doc = firebase_svc.db.collection('devices').document(device_id).get()
        if not device_doc.exists:
            log.error(f"Command failed: Device {device_id} not found")
            return False
            
        data = device_doc.to_dict()
        dev_type = data.get('type', 'gateway')
        
        topic = ""
        payload_dict = {"i": index, "s": state}

        if dev_type == 'satellite':
            parent_id = data.get('parent_gateway')
            if not parent_id:
                log.error(f"Satellite {device_id} has no parent gateway!")
                return False
                
            # ROUTE THROUGH GATEWAY
            topic = f"cmd/{parent_id}/set"
            payload_dict["target"] = device_id # Add target flag
            log.info(f"Routing command for {device_id} via Gateway {parent_id}")
            
        else:
            # DIRECT CONTROL
            topic = f"cmd/{device_id}/set"

        payload = json.dumps(payload_dict)
        
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

    def send_adoption_command(self, gateway_id: str, orphan_mac: str, user_uid: str):
        """
        Tells the Gateway to transmit the Adoption Ticket via ESP-NOW.
        """
        topic = f"cmd/{gateway_id}/set"
        payload = json.dumps({
            "hive_adopt": {
                "mac": orphan_mac,
                "uid": user_uid
            }
        })
        # QOS 1 ensures delivery to Gateway
        return self.client.publish(topic, payload, qos=1)

    def publish_calibration(self, device_id: str, target_voltage: float):
        # Check if Satellite
        from app.services.firebase_svc import firebase_svc
        device_doc = firebase_svc.db.collection('devices').document(device_id).get()
        if not device_doc.exists: return False
        
        data = device_doc.to_dict()
        dev_type = data.get('type', 'gateway')
        
        payload_dict = {"calib": target_voltage}
        topic = ""

        if dev_type == 'satellite':
            parent_id = data.get('parent_gateway')
            if not parent_id: return False
            
            topic = f"cmd/{parent_id}/set"
            payload_dict["target"] = device_id # Add Target
        else:
            topic = f"cmd/{device_id}/set"

        payload = json.dumps(payload_dict)
        return self.client.publish(topic, payload, qos=1)

mqtt_svc = MqttService()