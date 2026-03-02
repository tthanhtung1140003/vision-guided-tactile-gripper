import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
import random

DATA_FILE = "train_data.txt"
BATCH_SIZE = 64
EPOCHS = 200
LR = 1e-3
WEIGHT_DECAY = 1e-4
LOSS_WEIGHT = np.array([1.0, 1.0, 1.4], dtype=np.float32)  # Fx Fy Fz
VAL_SPLIT = 0.2
SEED = 42
DEVICE = "cpu"   
np.random.seed(SEED)
torch.manual_seed(SEED)
random.seed(SEED)

data = np.loadtxt(DATA_FILE).astype(np.float32)

X = data[:, :-3]
y = data[:, -3:]

print("Dataset:", X.shape, y.shape)

X_train, X_val, y_train, y_val = train_test_split(
    X, y, test_size=VAL_SPLIT, random_state=SEED, shuffle=True
)

x_scaler = StandardScaler()
y_scaler = StandardScaler()

X_train = x_scaler.fit_transform(X_train)
X_val   = x_scaler.transform(X_val)

y_train = y_scaler.fit_transform(y_train)
y_val   = y_scaler.transform(y_val)

class ForceDataset(Dataset):
    def __init__(self, X, y):
        self.X = torch.from_numpy(X)
        self.y = torch.from_numpy(y)

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]

train_loader = DataLoader(
    ForceDataset(X_train, y_train),
    batch_size=BATCH_SIZE,
    shuffle=True,
    drop_last=True
)

val_loader = DataLoader(
    ForceDataset(X_val, y_val),
    batch_size=BATCH_SIZE,
    shuffle=False
)

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

model = ForceMLP(X.shape[1]).to(DEVICE)

class WeightedSmoothL1(nn.Module):
    def __init__(self, weights_np):
        super().__init__()
        self.register_buffer(
            "w", torch.from_numpy(weights_np)
        )

    def forward(self, pred, target):
        loss = nn.functional.smooth_l1_loss(
            pred, target, reduction="none"
        )
        return torch.mean(loss * self.w)

criterion = WeightedSmoothL1(LOSS_WEIGHT).to(DEVICE)

optimizer = torch.optim.Adam(
    model.parameters(),
    lr=LR,
    weight_decay=WEIGHT_DECAY
)

best_val = np.inf
patience = 20
pat_cnt = 0

for epoch in range(EPOCHS):
    # ---- TRAIN ----
    model.train()
    train_loss = 0.0

    for xb, yb in train_loader:
        xb = xb.to(DEVICE)
        yb = yb.to(DEVICE)

        pred = model(xb)
        loss = criterion(pred, yb)

        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
        optimizer.step()

        train_loss += loss.item() * len(xb)

    train_loss /= len(train_loader.dataset)

    # ---- VAL ----
    model.eval()
    val_loss = 0.0
    with torch.no_grad():
        for xb, yb in val_loader:
            xb = xb.to(DEVICE)
            yb = yb.to(DEVICE)
            pred = model(xb)
            loss = criterion(pred, yb)
            val_loss += loss.item() * len(xb)

    val_loss /= len(val_loader.dataset)

    if epoch % 10 == 0:
        print(
            f"Epoch {epoch:03d} | "
            f"Train {train_loss:.4f} | "
            f"Val {val_loss:.4f}"
        )

    if val_loss < best_val:
        best_val = val_loss
        pat_cnt = 0
    else:
        pat_cnt += 1
        if pat_cnt >= patience:
            print("⏹ Early stopping")
            break

torch.save(
    {
        "model": model.state_dict(),

        "x_mean": x_scaler.mean_.astype(np.float32),
        "x_std":  x_scaler.scale_.astype(np.float32),
        "y_mean": y_scaler.mean_.astype(np.float32),
        "y_std":  y_scaler.scale_.astype(np.float32),

        "feature_dim": X.shape[1],
    },
    "force_mlp.pt",
)

print("Saved: force_mlp.pt")

model.eval()

abs_err_list = []

with torch.no_grad():
    for xb, yb in val_loader:
        xb = xb.to(DEVICE)
        yb = yb.to(DEVICE)

        pred_norm = model(xb)

        # ---- inverse normalize ----
        pred = (
            pred_norm.cpu().numpy() * y_scaler.scale_
            + y_scaler.mean_
        )
        gt = (
            yb.cpu().numpy() * y_scaler.scale_
            + y_scaler.mean_
        )

        abs_err_list.append(np.abs(pred - gt))

abs_err = np.concatenate(abs_err_list, axis=0)
mae = abs_err.mean(axis=0)

print("\n📊 Validation MAE (REAL UNIT):")
print(f"MAE Fx = {mae[0]:.4f}")
print(f"MAE Fy = {mae[1]:.4f}")
print(f"MAE Fz = {mae[2]:.4f}")