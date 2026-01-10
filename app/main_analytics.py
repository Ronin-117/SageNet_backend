import time
import schedule
from datetime import datetime, timedelta, timezone
from app.services.firebase_svc import firebase_svc
from app.services.influx_svc import influx_svc
from app.services.anomaly_svc import anomaly_svc
from app.core.config import settings
from app.core.logger import setup_logger

log = setup_logger("AnalyticsWorker")

def job_calculate_bills():
    """Runs hourly to update billing stats"""
    log.info("💰 Starting Hourly Billing Calculation...")
    try:
        # Fetch all devices (In prod, use pagination or a specific collection query)
        # For now, we iterate known devices from Firestore
        devices_ref = firebase_svc.db.collection('devices')
        for doc in devices_ref.stream():
            device_id = doc.id
            # ... (Insert your billing logic/service call here) ...
            # For this step, we focus on Anomaly logic
            pass 
    except Exception as e:
        log.error(f"Billing Job Failed: {e}")

def job_anomaly_lifecycle():
    """
    Runs every minute.
    Manages the State Machine: LEARNING -> TRAINING -> MONITORING
    """
    try:
        devices_ref = firebase_svc.db.collection('devices')
        
        for doc in devices_ref.stream():
            dev_data = doc.to_dict()
            device_id = doc.id
            
            # 1. Check Connectivity (Skip if offline > 5 mins)
            last_contact = dev_data.get('last_contact')
            if last_contact:
                # Firestore timestamp to datetime
                last_seen = last_contact.replace(tzinfo=timezone.utc)
                if (datetime.now(timezone.utc) - last_seen).total_seconds() > 300:
                    continue # Offline, skip

            # 2. Iterate Channels
            ai_config = dev_data.get('ai_config', {})
            live_state = dev_data.get('live_state', [0]*4)
            last_switched = dev_data.get('last_switched_on', [None]*4)

            for ch_str, config in ai_config.items():
                channel = int(ch_str)
                status = config.get('status', 'disabled')

                # --- STATE: LEARNING ---
                if status == 'learning':
                    # Check if time is up
                    training_end_str = config.get('training_end') # Firestore might return datetime or str
                    
                    # Handle Firestore Timestamp vs ISO String
                    if isinstance(training_end_str, str):
                        training_end = datetime.fromisoformat(training_end_str)
                    else:
                        training_end = training_end_str

                    if training_end and datetime.now(timezone.utc) > training_end.replace(tzinfo=timezone.utc):
                        log.info(f"[{device_id} Ch{channel}] Learning complete. Switching to TRAINING.")
                        firebase_svc.update_ai_status(device_id, channel, "training")

                # --- STATE: TRAINING ---
                elif status == 'training':
                    # Fetch active power data
                    # We look back 7 days (168h) by default to ensure we catch ALL recent data
                    # regardless of how long the learning period was extended.
                    data = influx_svc.get_training_data(device_id, channel, hours=168)
                    
                    # Requirement: 5 sequences of 24 points = 120 points
                    min_points = settings.ANOMALY_SEQUENCE_LENGTH * 5
                    
                    if len(data) >= min_points: 
                        threshold = anomaly_svc.train_model(device_id, channel, data)
                        if threshold > 0:
                            firebase_svc.update_ai_status(
                                device_id, channel, "monitoring", threshold=threshold
                            )
                    else:
                        # --- SELF-HEALING LOGIC ---
                        log.warning(f"[{device_id} Ch{channel}] Insufficient data ({len(data)}/{min_points}). Extending learning.")
                        
                        # Extend deadline by 12 hours
                        new_end_time = datetime.now(timezone.utc) + timedelta(hours=12)
                        
                        # Switch back to LEARNING
                        firebase_svc.update_ai_status(
                            device_id=device_id, 
                            channel=channel, 
                            status="learning", 
                            training_end=new_end_time
                        )

                # --- STATE: MONITORING ---
                elif status == 'monitoring':
                    # Only check if physically ON
                    if channel < len(live_state) and live_state[channel] == 1:
                        
                        # WARM-UP CHECK
                        warmup_ok = True
                        if channel < len(last_switched) and last_switched[channel]:
                            switched_time = datetime.fromisoformat(last_switched[channel])
                            diff_min = (datetime.now(timezone.utc) - switched_time).total_seconds() / 60
                            
                            if diff_min < settings.ANOMALY_WARMUP_MINUTES:
                                warmup_ok = False
                                # log.debug(f"Warming up... {diff_min:.1f}m")

                        if warmup_ok:
                            # Fetch sequence
                            seq = influx_svc.get_inference_sequence(device_id, channel)
                            is_anomaly, error, thresh = anomaly_svc.detect(device_id, channel, seq)
                            
                            if is_anomaly:
                                log.critical(f"⚠️ ANOMALY [{device_id} Ch{channel}] Err: {error:.2f} > {thresh:.2f}")
                                # TODO: Send Firebase Notification here
    
    except Exception as e:
        log.error(f"Anomaly Lifecycle Error: {e}")

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