#!/usr/bin/env bash
#
# MK Training — AWS Instance Setup Script
#
# Run this ONCE on a fresh AWS GPU instance to install all dependencies.
# Designed for: g5.xlarge (A10G 24GB) or g4dn.xlarge (T4 16GB)
# AMI: Deep Learning AMI (Ubuntu) or Amazon Linux 2 with GPU
#
# Usage:
#   chmod +x setup.sh
#   ./setup.sh
#
# After setup, run: ./train.sh
#

set -euo pipefail

echo "=============================================="
echo "  MK Training Environment Setup"
echo "=============================================="
echo ""

# Detect if CUDA is available
if command -v nvidia-smi &>/dev/null; then
    echo "[OK] NVIDIA GPU detected:"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
    echo ""
else
    echo "[ERROR] No NVIDIA GPU found!"
    echo "Make sure you launched a g5.xlarge or g4dn.xlarge instance."
    exit 1
fi

# Update system
echo "[1/5] Updating system packages..."
if command -v apt-get &>/dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq git python3-pip python3-venv
elif command -v dnf &>/dev/null; then
    sudo dnf update -y -q
    sudo dnf install -y -q git python3-pip
fi

# Create working directory
echo "[2/5] Setting up working directory..."
WORK_DIR="$HOME/mk-training"
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

# Create virtual environment
echo "[3/5] Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install PyTorch with CUDA
echo "[4/5] Installing PyTorch + CUDA..."
pip install --upgrade pip -q
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121 -q

# Install training dependencies
echo "[5/5] Installing training dependencies..."
pip install \
    transformers>=4.40.0 \
    peft>=0.10.0 \
    bitsandbytes>=0.43.0 \
    datasets>=2.18.0 \
    trl>=0.8.0 \
    accelerate>=0.28.0 \
    scipy \
    sentencepiece \
    protobuf \
    -q

echo ""
echo "=============================================="
echo "  Setup complete!"
echo "=============================================="
echo ""
echo "  Working directory: $WORK_DIR"
echo "  Python: $(python --version)"
echo "  PyTorch: $(python -c 'import torch; print(torch.__version__)')"
echo "  CUDA available: $(python -c 'import torch; print(torch.cuda.is_available())')"
echo "  GPU: $(python -c 'import torch; print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else "None")')"
echo ""
echo "  Next: Upload your training data and run ./train.sh"
echo ""
