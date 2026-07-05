#!/usr/bin/env bash
#
# MK Training — Launch Fine-Tuning
#
# Run this after setup.sh to start the actual training.
# Expects training data in ~/mk-training/data/
#
# Usage:
#   ./train.sh
#
# Or with custom options:
#   ./train.sh --epochs 5 --lr 1e-4 --lora_r 32
#

set -euo pipefail

WORK_DIR="$HOME/mk-training"
cd "$WORK_DIR"

# Activate virtual environment
source venv/bin/activate

echo "=============================================="
echo "  MK Fine-Tuning — Starting Training"
echo "=============================================="
echo ""

# Verify data exists
if [ ! -f "data/mk_train.jsonl" ]; then
    echo "[ERROR] Training data not found at data/mk_train.jsonl"
    echo ""
    echo "Upload your training data:"
    echo "  scp -r training/data/* ubuntu@<instance-ip>:~/mk-training/data/"
    echo ""
    exit 1
fi

# Verify GPU
python -c "
import torch
assert torch.cuda.is_available(), 'CUDA not available!'
gpu = torch.cuda.get_device_name(0)
vram = torch.cuda.get_device_properties(0).total_mem / 1e9
print(f'  GPU: {gpu} ({vram:.1f}GB VRAM)')
"

echo "  Train data: $(wc -l < data/mk_train.jsonl) examples"
echo "  Val data:   $(wc -l < data/mk_val.jsonl) examples"
echo ""

# Set optimal environment variables
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export TOKENIZERS_PARALLELISM=false

# Record start time
START_TIME=$(date +%s)

# Run training (pass through any extra args)
python scripts/finetune.py \
    --data_dir ./data \
    --output_dir ./output/mk-qwen-3b \
    "$@"

# Record end time
END_TIME=$(date +%s)
ELAPSED=$(( END_TIME - START_TIME ))
MINUTES=$(( ELAPSED / 60 ))

echo ""
echo "=============================================="
echo "  Training completed in ${MINUTES} minutes!"
echo "=============================================="
echo ""
echo "  Output:"
echo "    LoRA adapter:  ./output/mk-qwen-3b/"
echo "    Merged model:  ./output/mk-qwen-3b-merged/"
echo ""
echo "  Next step: Quantize the model"
echo "    python scripts/quantize.py --model_dir ./output/mk-qwen-3b-merged"
echo ""
echo "  Or download the merged model to your local machine:"
echo "    scp -r ubuntu@<instance-ip>:~/mk-training/output/mk-qwen-3b-merged ."
echo ""
