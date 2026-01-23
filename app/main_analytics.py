import time
import schedule
from datetime import datetime, timedelta, timezone
from app.services.firebase_svc import firebase_svc
from app.services.influx_svc import influx_svc
from app.services.anomaly_svc import anomaly_svc
from app.core.config import settings
from app.core.logger import setup_logger
from app.services.tariff_manager import tariff_mgr
from app.services.forecast_svc import forecast_svc
from firebase_admin import firestore

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

                        # log.info(f"Processing {device_id} Ch{channel} [{status}]")

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
                            current_val = live_state[channel] if channel < len(live_state) else 0
                            
                            is_active = False
                            try: is_active = int(current_val) == 1
                            except: pass

                            if is_active:
                                # ONLY LOG NOW - WHEN WE ACTUALLY DO SOMETHING
                                log.info(f"[{device_id} Ch{channel}] Monitoring Active (Device ON)")
                                
                                warmup_ok = True
                                if channel < len(last_switched) and last_switched[channel]:
                                    try:
                                        switched_time = datetime.fromisoformat(last_switched[channel])
                                        diff_min = (datetime.now(timezone.utc) - switched_time).total_seconds() / 60
                                        if diff_min < settings.ANOMALY_WARMUP_MINUTES: 
                                            warmup_ok = False
                                            log.info(f"   -> Warming up ({diff_min:.1f}m left)")
                                    except: pass
                                
                                if warmup_ok:
                                    seq = influx_svc.get_inference_sequence(device_id, channel)
                                    is_anomaly, error, thresh, pred, actual = anomaly_svc.detect(device_id, channel, seq)

                                    avg_hist = sum(seq) / len(seq) if seq else 0.0
                                    
                                    log.info(f"[{device_id} Ch{channel}] Stats -> Act: {actual:.2f}W | Pred: {pred:.2f}W | Avg(24m): {avg_hist:.2f}W | Thresh: {thresh:.2f}")

                                    if is_anomaly:
                                        log.critical(f"⚠️ ANOMALY [{device_id} Ch{channel}] Err: {error:.2f} > {thresh:.2f}")
                                        # 1. Get Owner ID (Required to save to correct user)
                                        owner_id = dev_data.get('owner_id')
                                        
                                        if owner_id:
                                            # 2. Construct Alert Data
                                            alert_payload = {
                                                "title": "⚠️ Unusual Power Detected",
                                                "body": f"Channel {channel} spiked to {actual:.1f}W (Expected {pred:.1f}W)",
                                                "device_id": device_id,
                                                "channel": channel, 
                                                "severity": "critical"
                                            }

                                            # 3. Save to History (The 3-month log)
                                            firebase_svc.save_alert(owner_id, alert_payload)

                                            # 4. Send Push Notification (Existing logic)
                                            firebase_svc.send_alert(device_id, alert_payload["title"], alert_payload["body"],channel )
                                        else:
                                            log.warning(f"Anomaly detected for {device_id} but no owner_id found.")
                            else:
                                # Device is OFF. Silence.
                                pass

                    except Exception as e:
                        log.error(f"Error processing Channel {channel} on {device_id}: {e}")
                        continue # Continue to next channel

            except Exception as e:
                log.error(f"Error processing Device {device_id}: {e}")
                continue # Continue to next device

    except Exception as e:
        log.error(f"CRITICAL LOOP FAILURE: {e}")


def job_calculate_bills():
    log.info("💰 Starting Hourly Billing Calculation...")
    try:
        users_ref = firebase_svc.db.collection('users')
        users_list = list(users_ref.stream())
        
        for doc in users_list:
            user_data = doc.to_dict()
            uid = doc.id
            
            # 1. Config (Safely get nested dicts)
            location = user_data.get('location', {})
            # Default to Kerala/India if missing
            country_code = location.get('country', 'IN')
            state_code = location.get('state', 'KL')

            bill_config = user_data.get('billing_config', {})
            
            # --- FIX 1: DYNAMIC BILLING CYCLE ---
            # Get the user's specific start day (default to 1st)
            start_day = int(bill_config.get('cycle_start_day', 1))
            today = datetime.now()
            
            # Calculate days passed in THIS cycle
            if today.day >= start_day:
                # Same month (e.g. Start 5th, Today 23rd -> 18 days)
                days_passed = today.day - start_day
            else:
                # Overlap from prev month (e.g. Start 20th, Today 5th -> ~15 days)
                # Approximation: 30 days in prev month
                days_passed = 30 - start_day + today.day
            
            # Ensure at least 1 day of data is looked at
            if days_passed < 1: days_passed = 1

            # 2. Get Data (Last 60 days history)
            history = influx_svc.get_user_daily_usage(uid, days=60)
            
            if not history:
                continue

            # 3. Filter for Current Bill Cycle
            # Slice the history based on calculated days_passed
            slice_idx = -days_passed if len(history) >= days_passed else 0
            current_cycle_usage = history[slice_idx:] 
            
            # Sum up (Convert to standard float immediately)
            current_month_kwh = float(sum(current_cycle_usage))
            
            # 4. Forecast
            # forecast_svc returns a float (or numpy float), we cast it to be safe
            predicted_total_kwh = float(forecast_svc.predict_month_end(history))
            
            # 5. Calculate Price
            bill_real_now = float(tariff_mgr.calculate_bill(
                country_code, state_code, current_month_kwh, bill_config
            ))
            bill_predicted = float(tariff_mgr.calculate_bill(
                country_code, state_code, predicted_total_kwh, bill_config
            ))

            # --- FIX 2: BUDGET GOAL ---
            # Get budget from config (Default 3000)
            budget_goal = float(bill_config.get('monthly_budget', 3000.0))

            # 6. Save (Now includes budget_goal for Frontend)
            firebase_svc.db.collection('billing_reports').document(uid).set({
                'currency': 'INR',
                'current_kwh': round(current_month_kwh, 2),
                'predicted_kwh': round(predicted_total_kwh, 2),
                'current_bill': round(bill_real_now, 2),
                'predicted_bill': round(bill_predicted, 2),
                
                # Critical for the "Budget Bar" in UI
                'budget_goal': round(budget_goal, 2),
                
                'last_updated': firestore.SERVER_TIMESTAMP
            }, merge=True)
            
            log.info(f"User {uid}: Used {current_month_kwh:.2f} kWh (₹{bill_real_now:.2f}) -> Budget: {budget_goal}")

    except Exception as e:
        # exc_info=True helps debug crashes
        log.error(f"Billing Job Error: {e}", exc_info=True)

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
