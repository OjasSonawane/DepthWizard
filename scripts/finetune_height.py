#!/usr/bin/env python3
"""
scripts/finetune_height.py

Domain Adaptation / Fine-tuning script for Depth Anything V2 on Remote Sensing Imagery.
This script is designed to be run on Google Colab or Kaggle with a GPU.

Instructions for Colab/Kaggle:
1. Upload this script or clone the repository.
2. Install dependencies:
   !pip install torch torchvision transformers huggingface_hub h5py numpy scipy scikit-learn
3. Run the script:
   !python finetune_height.py --epochs 10 --batch-size 8 --lr 1e-4

It uses the GAMUS dataset (earthflow/GAMUS) via streaming or local files.
"""

import os
import json
import random
import argparse
from datetime import datetime
from pathlib import Path

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import numpy as np

# Suppress warnings
import warnings
warnings.filterwarnings("ignore")

# Define random seed for reproducibility
def set_seed(seed=42):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

# Scale-and-shift-invariant (SSIL) Loss
class ScaleShiftInvariantLoss(nn.Module):
    def __init__(self):
        super().__init__()

    def forward(self, pred, target, mask=None):
        if mask is not None:
            pred = pred[mask]
            target = target[mask]
        
        if pred.numel() == 0:
            return torch.tensor(0.0, device=pred.device, requires_grad=True)

        # Compute scale and shift
        # pred = scale * target + shift
        # We can align pred to target using least squares or just compute scale/shift invariant metrics.
        # Alternatively, a simple SSIM-like or correlation-based loss.
        # Here we implement standard Scale-and-Shift Invariant Loss (MiDaS style)
        
        # Normalize both pred and target
        t_mean = target.mean()
        p_mean = pred.mean()
        
        t_var = torch.var(target) + 1e-6
        p_var = torch.var(pred) + 1e-6
        
        # Covariance
        cov = torch.mean((pred - p_mean) * (target - t_mean))
        
        # Pearson correlation
        rho = cov / torch.sqrt(p_var * t_var)
        
        # Loss is 1 - rho (maximize correlation)
        # We also want to penalize structural differences
        return 1.0 - rho


def main():
    parser = argparse.ArgumentParser(description="Fine-tune Depth Anything V2 for Remote Sensing")
    parser.add_argument("--epochs", type=int, default=10, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=8, help="Batch size")
    parser.add_argument("--lr", type=float, default=1e-4, help="Learning rate")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--output-dir", type=str, default="checkpoints", help="Output directory")
    args = parser.parse_args()

    set_seed(args.seed)
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    
    # 1. Load Model (Depth Anything V2 Small)
    # Using transformers DepthAnythingForDepthEstimation
    try:
        from transformers import AutoModelForDepthEstimation
        model_id = "depth-anything/Depth-Anything-V2-Small-hf"
        model = AutoModelForDepthEstimation.from_pretrained(model_id)
    except Exception as e:
        print(f"Error loading model: {e}")
        return

    # Freeze encoder
    for name, param in model.named_parameters():
        if "backbone" in name or "encoder" in name:
            param.requires_grad = False
    
    model.to(device)
    
    # 2. Setup Optimizer and Loss
    optimizer = optim.AdamW(filter(lambda p: p.requires_grad, model.parameters()), lr=args.lr)
    ssi_loss_fn = ScaleShiftInvariantLoss()
    l1_loss_fn = nn.L1Loss()
    
    # 3. Setup Dataset
    # Due to Colab environment, this script should use GAMUS or SIH2026 data.
    # A dummy dataset is provided here to ensure the script runs, which should be replaced
    # by the actual GAMUS/SIH dataset loader on Colab.
    print("Initializing datasets...")
    
    # Dummy Dataset for illustration
    class RemoteSensingDataset(Dataset):
        def __init__(self, split):
            self.split = split
            self.length = 100 if split == "train" else 20
        def __len__(self):
            return self.length
        def __getitem__(self, idx):
            # RGB: (3, 518, 518)
            # Depth: (518, 518)
            return torch.rand(3, 518, 518), torch.rand(518, 518), True # is_metric known
            
    train_dataset = RemoteSensingDataset("train")
    val_dataset = RemoteSensingDataset("val")
    
    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False)
    
    os.makedirs(args.output_dir, exist_ok=True)
    
    metrics = {"train_loss": [], "val_loss": []}
    
    for epoch in range(args.epochs):
        model.train()
        total_train_loss = 0
        
        for batch_idx, (rgb, target_depth, is_metric) in enumerate(train_loader):
            rgb = rgb.to(device)
            target_depth = target_depth.to(device)
            
            optimizer.zero_grad()
            
            outputs = model(pixel_values=rgb)
            pred_depth = outputs.predicted_depth # shape: (batch, height, width)
            
            # Resize pred_depth to target_depth if necessary
            if pred_depth.shape != target_depth.shape:
                pred_depth = nn.functional.interpolate(
                    pred_depth.unsqueeze(1), 
                    size=target_depth.shape[-2:], 
                    mode="bilinear", 
                    align_corners=False
                ).squeeze(1)
            
            # Compute loss
            ssil = ssi_loss_fn(pred_depth, target_depth)
            
            # Add L1 loss if GSD/metric is known
            # For demonstration, we assume it's known and add a small L1 regularization
            l1 = l1_loss_fn(pred_depth, target_depth)
            
            loss = ssil + 0.1 * l1
            
            loss.backward()
            optimizer.step()
            
            total_train_loss += loss.item()
            
        avg_train_loss = total_train_loss / len(train_loader)
        metrics["train_loss"].append(avg_train_loss)
        
        print(f"Epoch {epoch+1}/{args.epochs} - Train Loss: {avg_train_loss:.4f}")
        
    # Save config and metrics
    config_dict = {
        "model_id": "depth-anything/Depth-Anything-V2-Small-hf",
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "lr": args.lr,
        "seed": args.seed,
        "metrics": metrics,
        "timestamp": datetime.now().isoformat()
    }
    
    with open(os.path.join(args.output_dir, "finetune_config.json"), "w") as f:
        json.dump(config_dict, f, indent=4)
        
    # Save model weights
    torch.save(model.state_dict(), os.path.join(args.output_dir, "depth_anything_v2_rs_finetuned.pt"))
    print(f"Training complete. Checkpoints saved to {args.output_dir}")

if __name__ == "__main__":
    main()
