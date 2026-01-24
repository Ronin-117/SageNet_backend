import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import numpy as np
import os
import gc # Garbage Collection
from app.core.logger import setup_logger
from app.core.config import settings

log = setup_logger("AnomalyService")

# --- MODEL ARCHITECTURE ---
class TransformerForecaster(nn.Module):
    def __init__(self, input_dim=1, d_model=64, nhead=4, num_layers=2):
        super().__init__()
        self.encoder = nn.Linear(input_dim, d_model)
        encoder_layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=nhead, dim_feedforward=128)
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.decoder = nn.Linear(d_model, 1)

    def forward(self, x):
        x = self.encoder(x)
        x = x.permute(1, 0, 2)
        x = self.transformer(x)
        return self.decoder(x[-1])

class AnomalyService:
    def __init__(self):
        # Ensure model directory exists
        if not os.path.exists(settings.MODEL_DIR):
            os.makedirs(settings.MODEL_DIR)

    def _get_model_path(self, device_id: str, channel: int):
        return f"{settings.MODEL_DIR}/{device_id}_{channel}.pth"

    def _get_thresh_path(self, device_id: str, channel: int):
        return f"{settings.MODEL_DIR}/{device_id}_{channel}_thresh.txt"

    def train_model(self, device_id: str, channel: int, data: list) -> float:
        """
        Trains model and calculates a PHYSICS-AWARE threshold.
        """
        seq_len = settings.ANOMALY_SEQUENCE_LENGTH
        if len(data) < (seq_len * 5):
            log.warning(f"Not enough data to train ({len(data)} points).")
            return 0.0

        log.info(f"Training started for {device_id} Ch {channel}...")

        # 1. Prepare Data
        X, y = [], []
        for i in range(len(data) - seq_len):
            X.append(data[i : i+seq_len])
            y.append(data[i+seq_len])
        
        X_tensor = torch.tensor(X, dtype=torch.float32).unsqueeze(-1)
        y_tensor = torch.tensor(y, dtype=torch.float32).unsqueeze(-1)
        
        # 2. Init Model
        model = TransformerForecaster()
        criterion = nn.MSELoss()
        optimizer = optim.Adam(model.parameters(), lr=0.001)
        
        # 3. Train
        model.train()
        for epoch in range(15):
            optimizer.zero_grad()
            pred = model(X_tensor)
            loss = criterion(pred, y_tensor)
            loss.backward()
            optimizer.step()
        
        # 4. Calculate Threshold (THE FIX)
        model.eval()
        with torch.no_grad():
            preds = model(X_tensor).squeeze().numpy()
            actuals = y_tensor.squeeze().numpy()
            
            # A. Statistical Threshold
            errors = np.abs(preds - actuals)
            stat_threshold = float(np.mean(errors) + 3 * np.std(errors))
            
            # B. Physics Threshold (Max 40% of the Average Load)
            avg_load = float(np.mean(actuals))
            physics_cap = avg_load * 0.40 
            
            # Safety: If load is tiny (e.g. 5W), 40% is too small (2W). 
            # We set a hard floor of 5W to prevent false alarms on noise.
            if physics_cap < 5.0:
                physics_cap = 5.0

            # C. Final Decision: Pick the TIGHTER one, but respect the floor
            # If Stat says 80W (Bad), and Physics says 20W (Good) -> Pick 20W.
            # If Stat says 2W (Too tight), and Physics says 5W -> Pick 5W.
            
            threshold = min(stat_threshold, physics_cap)
            
            # Double Safety: If stats were wildly wrong, use Physics Cap
            if stat_threshold > avg_load:
                threshold = physics_cap
                log.info(f"   -> Statistical threshold ({stat_threshold:.2f}) was crazy. Clamped to {threshold:.2f}")

        # 5. Save
        torch.save(model.state_dict(), self._get_model_path(device_id, channel))
        with open(self._get_thresh_path(device_id, channel), "w") as f:
            f.write(str(threshold))

        log.info(f"Training Complete. Load: {avg_load:.1f}W | Threshold: {threshold:.4f}W")
        
        del model, X_tensor, y_tensor
        gc.collect()
        
        return threshold

    def detect(self, device_id: str, channel: int, recent_data: list):
        """
        Loads model, runs inference, returns (is_anomaly, error, threshold, pred, actual).
        """
        seq_len = settings.ANOMALY_SEQUENCE_LENGTH

        # CHECK 1: Not enough data
        if len(recent_data) < (seq_len + 1):
            # FIX: Must return 5 values, not 3
            return False, 0.0, 0.0, 0.0, 0.0

        model_path = self._get_model_path(device_id, channel)
        thresh_path = self._get_thresh_path(device_id, channel)

        # CHECK 2: Model missing
        if not os.path.exists(model_path) or not os.path.exists(thresh_path):
            # FIX: Must return 5 values, not 3
            return False, 0.0, 0.0, 0.0, 0.0

        try:
            # 1. Load Threshold
            with open(thresh_path, "r") as f:
                threshold = float(f.read().strip())

            # 2. Load Model
            model = TransformerForecaster()
            model.load_state_dict(torch.load(model_path, map_location=torch.device('cpu')))
            model.eval()

            # 3. Inference
            input_seq = recent_data[-(seq_len+1):-1]
            target = recent_data[-1]

            inp_tensor = torch.tensor(input_seq, dtype=torch.float32).view(1, seq_len, 1)

            with torch.no_grad():
                pred = model(inp_tensor).item()

            error = abs(pred - target)
            is_anomaly = error > threshold

            # Cleanup
            del model
            gc.collect()

            # SUCCESS RETURN (Exactly 5 values)
            return is_anomaly, error, threshold, float(pred), float(target)

        except Exception as e:
            log.error(f"Inference failed: {e}")
            # ERROR RETURN (Exactly 5 values)
            return False, 0.0, 0.0, 0.0, 0.0

anomaly_svc = AnomalyService()