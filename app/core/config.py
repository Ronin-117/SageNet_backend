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

    # AI / Anomaly Config
    ANOMALY_SEQUENCE_LENGTH: int = 30   # How many past points to look at (e.g., 24 mins)
    ANOMALY_WARMUP_MINUTES: int = 1     # How long to ignore data after device turns ON (Inrush current)
    ANOMALY_DEFAULT_THRESHOLD: float = 0.5 
    
    # Paths
    MODEL_DIR: str = "app/ml/models"    # Where .pth files live

    class Config:
        env_file = ".env"

settings = Settings()