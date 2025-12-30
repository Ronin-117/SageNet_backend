from typing import List, Dict, Any
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from app.core.config import settings
from app.core.logger import setup_logger

log = setup_logger("InfluxService")

class InfluxService:
    def __init__(self):
        """
        Initialize the InfluxDB Client.
        We use SYNCHRONOUS writes for the Bridge to ensure data integrity
        before acknowledging the MQTT message.
        """
        try:
            self.client = InfluxDBClient(
                url=settings.INFLUX_URL,
                token=settings.INFLUX_TOKEN,
                org=settings.INFLUX_ORG
            )
            
            # Write API: Used by the Bridge (Ingestor)
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
            
            # Query API: Used by the API (Frontend Graphs)
            self.query_api = self.client.query_api()
            
            log.info("InfluxDB Service Initialized")
        except Exception as e:
            log.critical(f"Failed to connect to InfluxDB: {e}")
            raise e

    def write_telemetry(self, device_id: str, owner_id: str, data: dict) -> bool:
        """
        Parses the 'Slim JSON' from MQTT and writes to InfluxDB.
        Structure: energy_usage, tags=[device, owner], fields=[v, current_x, state_x]
        """
        try:
            # 1. Create the Data Point
            point = Point("energy_usage") \
                .tag("device_id", device_id) \
                .tag("owner_id", owner_id) \
                .field("voltage", float(data.get('v', 0))) \
                .field("rssi", float(data.get('r', -60))) # Default RSSI if missing

            # 2. Process Arrays (Currents, Power, States)
            # Incoming data['c'] = [0.5, 1.2, 0.0, ...]
            currents = data.get('c', [])
            voltage = float(data.get('v', 0))
            
            total_power = 0.0

            for i, current_val in enumerate(currents):
                c_val = float(current_val)
                p_val = c_val * voltage # Calculate Power (Watts)
                
                point.field(f"current_{i}", c_val)
                point.field(f"power_{i}", p_val)
                
                total_power += p_val

            # Add Total Power field (Useful for bill calc)
            point.field("total_power", total_power)

            # Process States
            states = data.get('s', [])
            for i, state_val in enumerate(states):
                point.field(f"state_{i}", int(state_val))

            # 3. Write to Database
            self.write_api.write(bucket=settings.INFLUX_BUCKET, record=point)
            log.info(f"💾 Telemetry saved for {device_id}")
            return True

        except Exception as e:
            log.error(f"⚠️ Write Error for {device_id}: {e}")
            return False

    def get_history(self, device_id: str, minutes: int = 60) -> List[Dict[str, Any]]:
        """
        Fetches historical Voltage and Total Power for the requested duration.
        Used by the Mobile App for graphs.
        """
        try:
            bucket = settings.INFLUX_BUCKET
            
            # Flux Query:
            # 1. Select Bucket & Time Range
            # 2. Filter by Measurement & Device
            # 3. Filter specific fields we want to graph (Voltage & Total Power)
            # 4. Pivot (Turn rows into columns so JSON is easier to read)
            query = f'''
            from(bucket: "{bucket}")
              |> range(start: -{minutes}m)
              |> filter(fn: (r) => r["_measurement"] == "energy_usage")
              |> filter(fn: (r) => r["device_id"] == "{device_id}")
              |> filter(fn: (r) => r["_field"] == "voltage" or r["_field"] == "total_power")
              |> pivot(rowKey:["_time"], colKey:["_field"], valueColumn:"_value")
              |> keep(columns: ["_time", "voltage", "total_power"])
              |> limit(n: 100)
            '''
            
            result = self.query_api.query(org=settings.INFLUX_ORG, query=query)
            
            history = []
            for table in result:
                for record in table.records:
                    # Clean up the timestamp to ISO format string
                    history.append({
                        "time": record.get_time().isoformat(),
                        "voltage": record["voltage"] if "voltage" in record else 0.0,
                        "power": record["total_power"] if "total_power" in record else 0.0
                    })
            
            return history

        except Exception as e:
            log.error(f"⚠️ Query Error for {device_id}: {e}")
            raise e

    def close(self):
        """Cleanup connection"""
        self.client.close()

# Singleton Instance
influx_svc = InfluxService()