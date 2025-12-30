from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # MQTT
    MQTT_BROKER: str
    MQTT_PORT: int
    MQTT_USER: str
    MQTT_PASS: str
    
    # InfluxDB
    INFLUX_URL: str
    INFLUX_TOKEN: str
    INFLUX_ORG: str
    INFLUX_BUCKET: str
    
    # Firebase
    FIREBASE_CRED: str = "serviceAccountKey.json"

    class Config:
        env_file = ".env"

settings = Settings()