import time
import schedule
from datetime import datetime, timedelta, timezone
from app.services.firebase_svc import firebase_svc
from app.services.influx_svc import influx_svc
from app.services.anomaly_svc import anomaly_svc
from app.core.config import settings
from app.core.logger import setup_logger
from app.services.tariffs.tariff_manager import tariff_mgr
from app.services.forecast_svc import forecast_svc

log = setup_logger("AnalyticsWorker")

def job_anomaly_lifecycle():
    """
    Runs every minute.
    ISOLATION UPDATE: Each device/channel is wrapped in try/except.
    """
    log.info("--- Starting Anomaly Cycle ---")
    
    try:
        # Fetch all devices snapshot
        devices_ref = firebase_svc.db.collection('devices')
        all_devices = list(devices_ref.stream())
        
        for doc in all_devices:
            device_id = doc.id
            
            # --- ISOLATION BLOCK: DEVICE LEVEL ---
            try:
                dev_data = doc.to_dict()
                
                # 1. Check Connectivity
                last_contact = dev_data.get('last_contact')
                if last_contact:
                    last_seen = last_contact.replace(tzinfo=timezone.utc)
                    if (datetime.now(timezone.utc) - last_seen).total_seconds() > 300:
                        # log.debug(f"Skipping {device_id} (Offline)")
                        continue 

                ai_config = dev_data.get('ai_config', {})
                live_state = dev_data.get('live_state', [0]*4)
                last_switched = dev_data.get('last_switched_on', [None]*4)

                # 2. Iterate Channels
                for ch_str, config in ai_config.items():
                    channel = int(ch_str)
                    
                    # --- ISOLATION BLOCK: CHANNEL LEVEL ---
                    try:
                        status = config.get('status', 'disabled')
                        
                        # Skip disabled to reduce log noise
                        if status == 'disabled': 
                            continue

                        log.info(f"Processing {device_id} Ch{channel} [{status}]")

                        # --- STATE: LEARNING ---
                        if status == 'learning':
                            training_end_str = config.get('training_end')
                            if isinstance(training_end_str, str):
                                training_end = datetime.fromisoformat(training_end_str)
                            else:
                                training_end = training_end_str

                            if training_end and datetime.now(timezone.utc) > training_end.replace(tzinfo=timezone.utc):
                                log.info(f"[{device_id} Ch{channel}] Time up. Switching to TRAINING.")
                                firebase_svc.update_ai_status(device_id, channel, "training")

                        # --- STATE: TRAINING ---
                        elif status == 'training':
                            # Look back 7 days to gather sparse data
                            data = influx_svc.get_training_data(device_id, channel, hours=168)
                            
                            min_points = settings.ANOMALY_SEQUENCE_LENGTH * 5
                            
                            if len(data) >= min_points: 
                                log.info(f"[{device_id} Ch{channel}] Training with {len(data)} points...")
                                threshold = anomaly_svc.train_model(device_id, channel, data)
                                if threshold > 0:
                                    firebase_svc.update_ai_status(
                                        device_id, channel, "monitoring", threshold=threshold
                                    )
                            else:
                                log.warning(f"[{device_id} Ch{channel}] Insufficient Data ({len(data)}). Extending.")
                                new_end_time = datetime.now(timezone.utc) + timedelta(hours=12)
                                firebase_svc.update_ai_status(device_id, channel, "learning", training_end=new_end_time)

                        # --- STATE: MONITORING ---
                        elif status == 'monitoring':
                            if channel < len(live_state) and live_state[channel] == 1:
                                
                                # Warm-up Check
                                warmup_ok = True
                                if channel < len(last_switched) and last_switched[channel]:
                                    switched_time = datetime.fromisoformat(last_switched[channel])
                                    diff_min = (datetime.now(timezone.utc) - switched_time).total_seconds() / 60
                                    
                                    if diff_min < settings.ANOMALY_WARMUP_MINUTES:
                                        warmup_ok = False
                                
                                if warmup_ok:
                                    seq = influx_svc.get_inference_sequence(device_id, channel)
                                    is_anomaly, error, thresh = anomaly_svc.detect(device_id, channel, seq)
                                    
                                    if is_anomaly:
                                        log.critical(f"⚠️ ANOMALY [{device_id} Ch{channel}] Err: {error:.2f} > {thresh:.2f}")
                                        firebase_svc.send_alert(
                                            device_id=device_id,
                                            title="⚠️ Energy Anomaly Detected",
                                            body=f"Unusual power usage detected on Channel {channel}. Check your appliance."
                                        )

                    except Exception as e:
                        log.error(f"Error processing Channel {channel} on {device_id}: {e}")
                        continue # Continue to next channel

            except Exception as e:
                log.error(f"Error processing Device {device_id}: {e}")
                continue # Continue to next device

    except Exception as e:
        log.error(f"CRITICAL LOOP FAILURE: {e}")

def job_calculate_bills():
    """Runs HOURLY. Calculates kWh, Forecasts Month-End, applies KSEB Tariffs."""
    log.info("💰 Starting Hourly Billing Calculation...")
    try:
        users_ref = firebase_svc.db.collection('users')
        users_list = list(users_ref.stream()) # Convert to list to check count
        
        log.info(f"💰 Found {len(users_list)} users in Firestore.")

        for doc in users_list:
            user_data = doc.to_dict()
            uid = doc.id
            log.info(f"   -> Processing User: {uid}")
            
            # 1. Get User Config
            location = user_data.get('location', {'country': 'IN', 'state': 'KL'})
            bill_config = user_data.get('billing_config', {'phase': '1', 'type': 'domestic'})
            
            # 2. Get Aggregated Usage
            log.info(f"      Fetching InfluxDB data for {uid}...")
            history = influx_svc.get_user_daily_usage(uid, days=30)
            
            # DEBUG: Print history
            log.info(f"      History Points: {len(history)} | Data: {history}")

            if not history:
                log.warning(f"      ⚠️ No energy data for user {uid}. Saving 0 bill.")
                current_month_kwh = 0.0
                predicted_total_kwh = 0.0
            else:
                current_month_kwh = sum(history)
                # 3. Forecast
                predicted_total_kwh = forecast_svc.predict_month_end(history)
            
            # 4. Calculate Bill
            bill_real_now = tariff_mgr.calculate_bill(
                location['country'], location['state'], current_month_kwh, bill_config
            )
            bill_predicted = tariff_mgr.calculate_bill(
                location['country'], location['state'], predicted_total_kwh, bill_config
            )

            # 5. Save
            firebase_svc.db.collection('billing_reports').document(uid).set({
                'currency': 'INR',
                'current_kwh': round(current_month_kwh, 2),
                'predicted_kwh': round(predicted_total_kwh, 2),
                'current_bill': bill_real_now,
                'predicted_bill': bill_predicted,
                'last_updated': firestore.SERVER_TIMESTAMP
            }, merge=True)
            
            log.info(f"      ✅ Saved: Used {current_month_kwh:.1f} kWh (₹{bill_real_now}) -> Forecast ₹{bill_predicted}")

    except Exception as e:
        log.error(f"Billing Job Error: {e}")

# --- MAIN LOOP ---
if __name__ == "__main__":
    log.info("🧠 Analytics Engine Started")
    
    # Schedule Jobs
    schedule.every(1).hours.do(job_calculate_bills)
    schedule.every(1).minutes.do(job_anomaly_lifecycle) # Check every minute

    # Initial Run (Optional, for testing)
    # job_anomaly_lifecycle()

    while True:
        schedule.run_pending()
        time.sleep(10)