# force_infer.py
import torch
import torch.nn as nn
import numpy as np
import os

# ================= PATH =================
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(THIS_DIR, ".."))

MODEL_PATH = os.path.join(
    PROJECT_ROOT,
    "models",
    "force",
    "force_mlp_safe.pt"
)

# ================= MODEL =================
class ForceMLP(nn.Module):
    def __init__(self, in_dim):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, 64),
            nn.ReLU(),
            nn.Dropout(0.1),

            nn.Linear(64, 32),
            nn.ReLU(),

            nn.Linear(32, 3)
        )

    def forward(self, x):
        return self.net(x)

# ================= EMA FILTER =================
class EMAFilter:
    def __init__(self, alpha=0.2):
        self.alpha = alpha
        self.prev = None

    def update(self, x):
        x = np.asarray(x, dtype=np.float32)

        if self.prev is None:
            self.prev = x
        else:
            self.prev = self.alpha * x + (1.0 - self.alpha) * self.prev

        return self.prev

# ================= LOAD CHECKPOINT =================
ckpt = torch.load(MODEL_PATH, map_location="cpu")

model = ForceMLP(ckpt["feature_dim"])
model.load_state_dict(ckpt["model"])
model.eval()

x_mean = ckpt["x_mean"]
x_std  = ckpt["x_std"]
y_mean = ckpt["y_mean"]
y_std  = ckpt["y_std"]

# ================= INIT EMA  =================
ema_filter = EMAFilter(alpha=0.4)

# ================= INFERENCE =================
def predict_force(feature_vec, use_ema=True):
    x = np.asarray(feature_vec, dtype=np.float32)
    x = (x - x_mean) / (x_std + 1e-8)
    x = torch.from_numpy(x).unsqueeze(0)

    with torch.no_grad():
        y = model(x).numpy()[0]

    y = y * y_std + y_mean

    if use_ema:
        y = ema_filter.update(y)

    return float(y[0]), float(y[1]), float(y[2])
