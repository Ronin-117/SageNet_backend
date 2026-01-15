import numpy as np
import pandas as pd
import xgboost as xgb
from datetime import datetime, timedelta
import calendar
from app.core.logger import setup_logger

log = setup_logger("ForecastService")

class ForecastService:
    def predict_month_end(self, daily_usage_history: list) -> float:
        """
        Input: List of daily kWh floats [5.2, 4.8, 6.1...] (Last 30 days)
        Output: Estimated Total kWh for the current month.
        """
        if not daily_usage_history:
            return 0.0

        try:
            # 1. Prepare Data
            # We map "Day of Month" to "Usage"
            today = datetime.now()
            days_in_month = calendar.monthrange(today.year, today.month)[1]
            current_day = today.day
            
            # Simple Logic: If we have very little data (< 3 days), use Average
            if len(daily_usage_history) < 3:
                avg = np.mean(daily_usage_history)
                return avg * days_in_month

            # 2. XGBoost Setup (Time Series Regression)
            # X = Day Index (1, 2, 3...), y = kWh
            df = pd.DataFrame({'day': range(1, len(daily_usage_history) + 1), 'kwh': daily_usage_history})
            
            model = xgb.XGBRegressor(n_estimators=50, max_depth=3)
            model.fit(df[['day']], df['kwh'])

            # 3. Predict Remaining Days
            future_days = range(len(daily_usage_history) + 1, days_in_month + 1)
            if not future_days:
                return sum(daily_usage_history) # End of month

            future_df = pd.DataFrame({'day': future_days})
            predictions = model.predict(future_df[['day']])
            
            # 4. Sum Actual + Predicted
            total_forecast = sum(daily_usage_history) + sum(predictions)
            return max(total_forecast, 0) # Safety (no negative energy)

        except Exception as e:
            log.error(f"XGBoost Error: {e}")
            # Fallback to simple linear projection
            avg = np.mean(daily_usage_history)
            return avg * days_in_month

forecast_svc = ForecastService()