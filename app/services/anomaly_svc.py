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
        Trains model on CPU, saves .pth, returns calculated threshold.
        """
        seq_len = settings.ANOMALY_SEQUENCE_LENGTH
        if len(data) < (seq_len * 5):
            log.warning(f"Not enough data to train ({len(data)} points). Need {seq_len*5}+")
            return 0.0

        log.info(f"Training started for {device_id} Ch {channel} with {len(data)} points...")

        # 1. Prepare Data
        X, y = [], []
        for i in range(len(data) - seq_len):
            X.append(data[i : i+seq_len])
            y.append(data[i+seq_len])
        
        X_tensor = torch.tensor(X, dtype=torch.float32).unsqueeze(-1)
        y_tensor = torch.tensor(y, dtype=torch.float32).unsqueeze(-1)
        
        # 2. Init Model (CPU)
        model = TransformerForecaster()
        criterion = nn.MSELoss()
        optimizer = optim.Adam(model.parameters(), lr=0.001)
        
        # 3. Train Loop
        epochs = 15
        model.train()
        for epoch in range(epochs):
            optimizer.zero_grad()
            pred = model(X_tensor)
            loss = criterion(pred, y_tensor)
            loss.backward()
            optimizer.step()
        
        # 4. Calculate Dynamic Threshold
        model.eval()
        with torch.no_grad():
            preds = model(X_tensor).squeeze().numpy()
            actuals = y_tensor.squeeze().numpy()
            errors = np.abs(preds - actuals)
            # Threshold = Mean Error + 3 Standard Deviations (99.7% confidence)
            threshold = float(np.mean(errors) + 3 * np.std(errors))

        # 5. Save Artifacts
        torch.save(model.state_dict(), self._get_model_path(device_id, channel))
        with open(self._get_thresh_path(device_id, channel), "w") as f:
            f.write(str(threshold))

        log.info(f"Training Complete. Threshold: {threshold:.4f}")
        
        # 6. Cleanup RAM
        del model
        del X_tensor
        del y_tensor
        gc.collect() # Force garbage collection
        
        return threshold

    def detect(self, device_id: str, channel: int, recent_data: list):
        """
        Loads model, runs inference, returns (is_anomaly, error).
        """
        seq_len = settings.ANOMALY_SEQUENCE_LENGTH
        if len(recent_data) < (seq_len + 1):
            return False, 0.0

        model_path = self._get_model_path(device_id, channel)
        thresh_path = self._get_thresh_path(device_id, channel)

        if not os.path.exists(model_path) or not os.path.exists(thresh_path):
            return False, 0.0

        try:
            # 1. Load Threshold
            with open(thresh_path, "r") as f:
                threshold = float(f.read().strip())

            # 2. Load Model (Lazy Load)
            model = TransformerForecaster()
            model.load_state_dict(torch.load(model_path, map_location=torch.device('cpu')))
            model.eval()

            # 3. Inference
            input_seq = recent_data[-(seq_len+1):-1] # Past N points
            target = recent_data[-1]                 # Current point
            
            inp_tensor = torch.tensor(input_seq, dtype=torch.float32).view(1, seq_len, 1)
            
            with torch.no_grad():
                pred = model(inp_tensor).item()
            
            error = abs(pred - target)
            is_anomaly = error > threshold

            # Cleanup
            del model
            gc.collect()

            return is_anomaly, error, threshold

        except Exception as e:
            log.error(f"Inference failed: {e}")
            return False, 0.0, 0.0

anomaly_svc = AnomalyService()