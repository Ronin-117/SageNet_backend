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

    def get_history(self, device_id: str, minutes: int = 60, channel: int = None) -> List[Dict[str, Any]]:
        try:
            bucket = settings.INFLUX_BUCKET
            
            # 1. Aggregation Logic
            aggregate = ""
            if minutes > 1440: 
                aggregate = '|> aggregateWindow(every: 1h, fn: mean, createEmpty: false)'
            elif minutes > 180: 
                aggregate = '|> aggregateWindow(every: 5m, fn: mean, createEmpty: false)'
            
            # 2. Field Selection
            if channel is not None:
                field_filter = f'r["_field"] == "power_{channel}"'
                target_power_field = f"power_{channel}"
            else:
                field_filter = 'r["_field"] == "voltage" or r["_field"] == "total_power"'
                target_power_field = "total_power"

            # 3. Query
            query = f'''
            from(bucket: "{bucket}")
              |> range(start: -{minutes}m)
              |> filter(fn: (r) => r["_measurement"] == "energy_usage")
              |> filter(fn: (r) => r["device_id"] == "{device_id}")
              |> filter(fn: (r) => {field_filter})
              {aggregate}
              |> sort(columns: ["_time"])
            '''
            
            result = self.query_api.query(org=settings.INFLUX_ORG, query=query)
            
            # 4. ROBUST MERGING (The Fix)
            merged_data = {}

            for table in result:
                for record in table.records:
                    # FIX: Strip microseconds to ensure Voltage & Power align
                    dt = record.get_time()
                    # Use standard format YYYY-MM-DDTHH:MM:SS (No micros)
                    time_key = dt.strftime('%Y-%m-%dT%H:%M:%SZ')
                    
                    if time_key not in merged_data:
                        merged_data[time_key] = {"time": time_key, "voltage": 0.0, "power": 0.0}
                    
                    field = record.get_field()
                    val = record.get_value() or 0.0

                    if field == "voltage":
                        merged_data[time_key]["voltage"] = round(val, 1)
                    elif field == target_power_field:
                        merged_data[time_key]["power"] = round(val, 2)

            # 5. Sort by time
            history_list = sorted(merged_data.values(), key=lambda x: x['time'])
            
            # Debug Log to verify data flow
            log.info(f"API History: Found {len(history_list)} points for {device_id} (Last: {history_list[-1] if history_list else 'None'})")
            
            return history_list

        except Exception as e:
            log.error(f"History Query Error: {e}", exc_info=True)
            return []
    
    def get_long_history(self, device_id: str, days: int) -> List[Dict[str, Any]]:
        """
        Fetches daily aggregated stats.
        FIX: Performs pivoting in Python to avoid InfluxDB syntax errors.
        """
        try:
            bucket = settings.INFLUX_BUCKET
            
            # 1. SIMPLE QUERY: No Pivot. Just aggregation.
            query = f'''
            from(bucket: "{bucket}")
              |> range(start: -{days}d)
              |> filter(fn: (r) => r["_measurement"] == "energy_usage")
              |> filter(fn: (r) => r["device_id"] == "{device_id}")
              |> filter(fn: (r) => r["_field"] == "voltage" or r["_field"] == "total_power")
              
              // 1. createEmpty: true -> Generates rows even if device was unplugged all day
              |> aggregateWindow(every: 1d, fn: mean, createEmpty: true)
              
              // 2. fill(value: 0.0) -> Replaces "null" with 0.0 so math works
              |> fill(value: 0.0)
            '''
            
            result = self.query_api.query(org=settings.INFLUX_ORG, query=query)
            
            # 2. Python-side Processing
            # We create a dictionary to group results by Date
            daily_stats = {}

            for table in result:
                for record in table.records:
                    # Get Date (YYYY-MM-DD)
                    date_key = record.get_time().date().isoformat()
                    field_name = record.get_field()
                    value = record.get_value() or 0.0

                    # Initialize if new date
                    if date_key not in daily_stats:
                        daily_stats[date_key] = {
                            "date": date_key, 
                            "avg_voltage": 0.0, 
                            "total_energy_kwh": 0.0
                        }
                    
                    # Fill data
                    if field_name == "voltage":
                        daily_stats[date_key]["avg_voltage"] = round(value, 1)
                    elif field_name == "total_power":
                        # Convert Mean Watts to Daily kWh: Watts * 24h / 1000
                        kwh = (value * 24.0) / 1000.0
                        daily_stats[date_key]["total_energy_kwh"] = round(kwh, 3)

            # 3. Convert dict to sorted list (Oldest to Newest)
            history = sorted(daily_stats.values(), key=lambda x: x['date'])
            
            return history

        except Exception as e:
            log.error(f"Long History Error: {e}")
            raise e

    def get_network_load(self, owner_uid: str) -> float:
        """
        Calculates total load. Widened range to -10m to prevent 0W dropouts.
        """
        try:
            bucket = settings.INFLUX_BUCKET
            # FIX: Changed -1m to -10m. 
            # We want the "Latest" value, even if it's 2 minutes old.
            query = f'''
            from(bucket: "{bucket}")
              |> range(start: -10m)
              |> filter(fn: (r) => r["_measurement"] == "energy_usage")
              |> filter(fn: (r) => r["owner_id"] == "{owner_uid}")
              |> filter(fn: (r) => r["_field"] == "total_power")
              |> last()
              |> group()
              |> sum() 
            '''
            
            result = self.query_api.query(org=settings.INFLUX_ORG, query=query)
            
            total_load = 0.0
            found = False
            for table in result:
                for record in table.records:
                    total_load = record.get_value() or 0.0
                    found = True
            
            # Debug Log to confirm we found the user's data
            if found:
                log.info(f"Network Load for {owner_uid}: {total_load} W")
            else:
                log.warning(f"Network Load for {owner_uid}: 0W (No data in last 10m)")
                
            return round(total_load, 2)
        except Exception as e:
            log.error(f"Network Load Error: {e}")
            return 0.0

    def get_network_history(self, owner_uid: str, minutes: int = 60) -> List[Dict[str, Any]]:
        try:
            bucket = settings.INFLUX_BUCKET
            
            if minutes > 1440: 
                every = "1h"
            elif minutes > 180: 
                every = "5m"
            else:
                every = "1m"

            # Query breakdown:
            # 1. Filter by Owner
            # 2. align all devices to same time grid (aggregateWindow)
            # 3. group by Time (merges all devices into one table per timestamp)
            # 4. sum the values in that table
            query = f'''
            from(bucket: "{bucket}")
              |> range(start: -{minutes}m)
              |> filter(fn: (r) => r["_measurement"] == "energy_usage")
              |> filter(fn: (r) => r["owner_id"] == "{owner_uid}")
              |> filter(fn: (r) => r["_field"] == "total_power")
              |> aggregateWindow(every: {every}, fn: mean, createEmpty: false)
              |> group(columns: ["_time"])
              |> sum()
              |> sort(columns: ["_time"])
            '''
            
            result = self.query_api.query(org=settings.INFLUX_ORG, query=query)
            
            history = []
            for table in result:
                for record in table.records:
                    dt = record.get_time()
                    # FIX: Add 'Z' for Frontend Timezone Parsing
                    time_str = dt.strftime('%Y-%m-%dT%H:%M:%SZ')
                    
                    history.append({
                        "time": time_str,
                        "active_load_watts": round(record.get_value() or 0.0, 2)
                    })
            
            log.info(f"Network History: {len(history)} points for {owner_uid}")
            return history

        except Exception as e:
            log.error(f"Network History Query Error: {e}", exc_info=True)
            return []
    
    def get_activity_patterns(self, device_id: str, days: int) -> Dict[str, List[Dict]]:
        """
        Fetches state activity grouped by 30-minute blocks.
        Used for Heatmaps/Usage Patterns.
        """
        try:
            bucket = settings.INFLUX_BUCKET
            
            # FLUX QUERY:
            # 1. Filter: specific device AND fields starting with "state_"
            # 2. Aggregate: Average (mean) over 30 mins.
            #    - Mean works perfectly: 1=Always On, 0=Always Off, 0.5=Half On.
            # 3. Fill: If unplugged, assume Off (0.0).
            
            query = f'''
            from(bucket: "{bucket}")
              |> range(start: -{days}d)
              |> filter(fn: (r) => r["_measurement"] == "energy_usage")
              |> filter(fn: (r) => r["device_id"] == "{device_id}")
              |> filter(fn: (r) => r["_field"] =~ /state_/)
              |> aggregateWindow(every: 30m, fn: mean, createEmpty: true)
              |> fill(value: 0.0)
            '''
            
            result = self.query_api.query(org=settings.INFLUX_ORG, query=query)
            
            # Organize by Channel Index
            # Structure: { "0": [points...], "1": [points...] }
            channels_data = {}

            for table in result:
                for record in table.records:
                    field = record.get_field() # e.g., "state_0"
                    
                    # Extract index from "state_0" -> "0"
                    channel_index = field.split("_")[1]
                    
                    if channel_index not in channels_data:
                        channels_data[channel_index] = []
                    
                    channels_data[channel_index].append({
                        "time": record.get_time().isoformat(),
                        "value": round(record.get_value(), 2) # 0.0 to 1.0
                    })
            
            return channels_data

        except Exception as e:
            log.error(f"Activity Query Error: {e}")
            raise e

    def get_training_data(self, device_id: str, channel: int, start_time: datetime) -> List[float]:
        """
        Fetches raw POWER data for training. 
        Filters out values < 5.0 Watts (Device OFF/Standby) to ensure model learns active patterns.
        """
        try:
            bucket = settings.INFLUX_BUCKET

            # Convert python datetime to Influx string format
            start_iso = start_time.strftime('%Y-%m-%dT%H:%M:%SZ')

            # Query: Get Power for specific channel, filtered by value > 5W
            query = f'''
            from(bucket: "{bucket}")
              |> range(start: {start_iso})
              |> filter(fn: (r) => r["_measurement"] == "energy_usage")
              |> filter(fn: (r) => r["device_id"] == "{device_id}")
              |> filter(fn: (r) => r["_field"] == "power_{channel}")
              |> filter(fn: (r) => r["_value"] > 5.0) 
            '''
            result = self.query_api.query(org=settings.INFLUX_ORG, query=query)
            
            data = []
            for table in result:
                for record in table.records:
                    data.append(record.get_value())
            
            return data
        except Exception as e:
            log.error(f"Training Data Fetch Error: {e}")
            return []

    def get_inference_sequence(self, device_id: str, channel: int) -> List[float]:
        """
        Fetches exact sequence length for live detection.
        """
        limit = settings.ANOMALY_SEQUENCE_LENGTH + 1
        try:
            bucket = settings.INFLUX_BUCKET
            # FIX: Removed comments inside the query string
            query = f'''
            from(bucket: "{bucket}")
              |> range(start: -2h)
              |> filter(fn: (r) => r["_measurement"] == "energy_usage")
              |> filter(fn: (r) => r["device_id"] == "{device_id}")
              |> filter(fn: (r) => r["_field"] == "power_{channel}")
              |> sort(columns: ["_time"], desc: true)
              |> limit(n: {limit})
            '''
            result = self.query_api.query(org=settings.INFLUX_ORG, query=query)
            
            data = []
            for table in result:
                for record in table.records:
                    data.append(record.get_value())
            
            return data[::-1] 

        except Exception as e:
            log.error(f"Inference Data Fetch Error: {e}")
            return []

    def get_user_daily_usage(self, owner_uid: str, days: int = 60) -> list:
        try:
            bucket = settings.INFLUX_BUCKET
            query = f'''
            from(bucket: "{bucket}")
              |> range(start: -{days}d)
              |> filter(fn: (r) => r["_measurement"] == "energy_usage")
              |> filter(fn: (r) => r["owner_id"] == "{owner_uid}")
              |> filter(fn: (r) => r["_field"] == "total_power")
              
              // 1. Group ALL series into one (Merge devices)
              |> group()
              
              // 2. Window by 1 Day. Take the MEAN (Average Power in Watts)
              |> aggregateWindow(every: 1d, fn: mean, createEmpty: false)
              
              // 3. Ensure we don't get duplicates
              |> unique(column: "_time")
              |> sort(columns: ["_time"])
            '''
            result = self.query_api.query(org=settings.INFLUX_ORG, query=query)
            
            usage = []
            for table in result:
                for record in table.records:
                    # Value is "Average Watts" for that day.
                    # Formula: Avg Watts * 24 Hours / 1000 = kWh
                    avg_watts = record.get_value() or 0.0
                    kwh = (avg_watts * 24.0) / 1000.0
                    usage.append(kwh)
            
            # DEBUG: Print how many days we found
            log.info(f"Daily Usage Points (Should be < {days}): {len(usage)}")
            
            return usage
        except Exception as e:
            log.error(f"User Usage Query Error: {e}")
            return []
            
    def close(self):
        self.client.close()

influx_svc = InfluxService()