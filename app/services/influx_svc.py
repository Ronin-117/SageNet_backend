from typing import List, Dict, Any
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from app.core.config import settings
from app.core.logger import setup_logger

log = setup_logger("InfluxService")

class InfluxService:
    def __init__(self):
        try:
            # Exactly how you had it in the old working code
            self.client = InfluxDBClient(
                url=settings.INFLUX_URL,
                token=settings.INFLUX_TOKEN,
                org=settings.INFLUX_ORG
            )
            
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
            self.query_api = self.client.query_api()
            
            log.info("✅ InfluxDB Service Initialized")
        except Exception as e:
            log.critical(f"❌ Failed to connect to InfluxDB: {e}")
            raise e

    def write_telemetry(self, device_id: str, owner_id: str, data: dict) -> bool:
        """
        Writes data to InfluxDB. 
        """
        try:
            point = Point("energy_usage") \
                .tag("device_id", device_id) \
                .tag("owner_id", owner_id) \
                .field("voltage", float(data.get('v', 0))) \
                .field("rssi", float(data.get('r', -60)))

            # Handle Arrays
            currents = data.get('c', [])
            voltage = float(data.get('v', 0))
            total_power = 0.0

            for i, current_val in enumerate(currents):
                c_val = float(current_val)
                p_val = c_val * voltage 
                point.field(f"current_{i}", c_val)
                point.field(f"power_{i}", p_val)
                total_power += p_val

            point.field("total_power", total_power)

            states = data.get('s', [])
            for i, state_val in enumerate(states):
                point.field(f"state_{i}", int(state_val))

            self.write_api.write(bucket=settings.INFLUX_BUCKET, record=point)
            log.info(f"💾 Telemetry saved for {device_id}")
            return True

        except Exception as e:
            log.error(f"⚠️ Write Error for {device_id}: {e}")
            return False

    def get_history(self, device_id: str, minutes: int = 60) -> List[Dict[str, Any]]:
        """
        Fetches history using the SIMPLE query from your old code.
        """
        try:
            bucket = settings.INFLUX_BUCKET
            
            # --- OLD WORKING QUERY ---
            # No pivot. No complexity. Just raw voltage data.
            query = f'''
            from(bucket: "{bucket}")
              |> range(start: -{minutes}m)
              |> filter(fn: (r) => r["_measurement"] == "energy_usage")
              |> filter(fn: (r) => r["device_id"] == "{device_id}")
              |> filter(fn: (r) => r["_field"] == "voltage")
              |> limit(n: 20)
            '''
            
            result = self.query_api.query(org=settings.INFLUX_ORG, query=query)
            
            history = []
            for table in result:
                for record in table.records:
                    history.append({
                        "time": record.get_time().isoformat(),
                        "voltage": record.get_value(),
                        "power": 0.0  # Placeholder to satisfy Schema
                    })
            
            return history

        except Exception as e:
            log.error(f"⚠️ Query Error for {device_id}: {e}")
            raise e
    
    def get_long_history(self, device_id: str, days: int) -> List[Dict[str, Any]]:
        """
        Fetches daily aggregated stats (Avg Voltage, Total Energy).
        """
        try:
            bucket = settings.INFLUX_BUCKET
            
            # FLUX QUERY EXPLANATION:
            # 1. Range: Last N days.
            # 2. Filter: Voltage OR Power.
            # 3. Aggregate: Group by 1 Day. 
            #    - For Voltage: Calculate Mean (Average).
            #    - For Power: Calculate Integral (Energy in Watt-Hours).
            
            query = f'''
            from(bucket: "{bucket}")
              |> range(start: -{days}d)
              |> filter(fn: (r) => r["_measurement"] == "energy_usage")
              |> filter(fn: (r) => r["device_id"] == "{device_id}")
              |> filter(fn: (r) => r["_field"] == "voltage" or r["_field"] == "total_power")
              
              |> aggregateWindow(every: 1d, fn: mean, createEmpty: false)
              
              |> pivot(rowKey:["_time"], columnKey:["_field"], valueColumn:"_value")
              |> keep(columns: ["_time", "voltage", "total_power"])
            '''
            
            result = self.query_api.query(org=settings.INFLUX_ORG, query=query)
            
            history = []
            for table in result:
                for record in table.records:
                    # Power is usually instantaneous Watts. 
                    # If we averaged Watts over a day, we effectively get Avg Watts.
                    # To get kWh roughly: Avg Watts * 24h / 1000.
                    avg_watts = record["total_power"] if "total_power" in record else 0.0
                    kwh = (avg_watts * 24) / 1000.0
                    
                    history.append({
                        "date": record.get_time().date().isoformat(), # Returns YYYY-MM-DD
                        "avg_voltage": round(record["voltage"], 1) if "voltage" in record else 0.0,
                        "total_energy_kwh": round(kwh, 3)
                    })
            
            return history

        except Exception as e:
            log.error(f"Long History Error: {e}")
            raise e

    def close(self):
        self.client.close()

influx_svc = InfluxService()