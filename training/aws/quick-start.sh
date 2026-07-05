#!/usr/bin/env bash
#
# MK Training — Quick Start (All-in-One)
#
# This is the SIMPLEST way to train MK's brain on AWS.
# Run this on the AWS instance after SSH-ing in.
#
# It does everything:
#   1. Clones the MK repo
#   2. Sets up the environment
#   3. Runs the training
#   4. Quantizes the model to GGUF
#   5. Tells you how to download the result
#
# Usage (on the AWS instance):
#   curl -sSL https://raw.githubusercontent.com/mohd2456/MK/main/training/aws/quick-start.sh | bash
#
# Or:
#   git clone https://github.com/mohd2456/MK.git
#   bash MK/training/aws/quick-start.sh
#

set -euo pipefail

echo ""
echo "  ███╗   ███╗██╗  ██╗    ████████╗██████╗  █████╗ ██╗███╗   ██╗"
echo "  ████╗ ████║██║ ██╔╝    ╚══██╔══╝██╔══██╗██╔══██╗██║████╗  ██║"
echo "  ██╔████╔██║█████╔╝        ██║   ██████╔╝███████║██║██╔██╗ ██║"
echo "  ██║╚██╔╝██║██╔═██╗        ██║   ██╔══██╗██╔══██║██║██║╚██╗██║"
echo "  ██║ ╚═╝ ██║██║  ██╗       ██║   ██║  ██║██║  ██║██║██║ ╚████║"
echo "  ╚═╝     ╚═╝╚═╝  ╚═╝       ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚═╝ ╚═══╝"
echo ""
echo "  MK Brain Training — Quick Start"
echo ""

START_TIME=$(date +%s)
WORK_DIR="$HOME/mk-training"

# Step 1: Clone repo if not already
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 1: Getting MK source code"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ ! -d "$HOME/MK" ]; then
    cd "$HOME"
    git clone https://github.com/mohd2456/MK.git
fi

# Step 2: Setup environment
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 2: Setting up training environment"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
mkdir -p "$WORK_DIR"/{data,scripts,output}

# Copy training files
cp "$HOME/MK/training/data/"*.jsonl "$WORK_DIR/data/"
cp "$HOME/MK/training/scripts/"*.py "$WORK_DIR/scripts/"
cp "$HOME/MK/training/scripts/requirements.txt" "$WORK_DIR/"

cd "$WORK_DIR"

# Create venv and install deps
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate

pip install --upgrade pip -q
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121 -q
pip install -r requirements.txt -q

# Verify GPU
python -c "
import torch
assert torch.cuda.is_available(), 'No GPU!'
print(f'  GPU: {torch.cuda.get_device_name(0)}')
print(f'  VRAM: {torch.cuda.get_device_properties(0).total_mem / 1e9:.1f}GB')
"

# Step 3: Train
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 3: Training MK's brain"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  This will take 1-3 hours. Go do something else."
echo ""

export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export TOKENIZERS_PARALLELISM=false

python scripts/finetune.py \
    --data_dir ./data \
    --output_dir ./output/mk-qwen-3b

# Step 4: Quantize
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Step 4: Quantizing to GGUF (for llama.cpp)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Install llama.cpp python for conversion
pip install llama-cpp-python -q 2>/dev/null || true

python scripts/quantize.py \
    --model_dir ./output/mk-qwen-3b-merged \
    --output_dir ./output/mk-gguf

# Done
END_TIME=$(date +%s)
ELAPSED=$(( (END_TIME - START_TIME) / 60 ))

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  DONE! MK's brain is ready."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "  Time: ${ELAPSED} minutes"
echo "  Output: $WORK_DIR/output/mk-gguf/"
echo ""
echo "  Download the model to your i5-3470:"
echo "    scp ubuntu@$(curl -s ifconfig.me):$WORK_DIR/output/mk-gguf/mk-brain-q4_k_m.gguf ."
echo ""
echo "  Then deploy on your machine (see training/deploy/)"
echo ""
echo "  REMEMBER: Terminate this AWS instance when done!"
echo "    exit"
echo "    aws ec2 terminate-instances --instance-ids <your-instance-id>"
echo ""
