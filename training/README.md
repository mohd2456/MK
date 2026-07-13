# MK Brain — Training Pipeline

> Fine-tune Qwen2.5-3B-Instruct into MK's personal decision-making brain.

This directory contains everything needed to train, quantize, and deploy MK's local LLM on the i5-3470.

---

## Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                    MK Brain Training Pipeline                      │
├──────────────────────────────────────────────────────────────────┤
│                                                                    │
│  ┌─────────┐    ┌──────────┐    ┌──────────┐    ┌────────────┐  │
│  │ Dataset │───▶│  Train   │───▶│ Quantize │───▶│  Deploy    │  │
│  │ (786    │    │  (QLoRA  │    │  (GGUF   │    │  (i5-3470  │  │
│  │  examples)   │  on AWS) │    │  Q4_K_M) │    │  llama.cpp)│  │
│  └─────────┘    └──────────┘    └──────────┘    └────────────┘  │
│                                                                    │
│  Cost: ~$3-10        Time: 1-3 hrs       Result: 3.5GB model     │
└──────────────────────────────────────────────────────────────────┘
```

---

## Quick Start (The Fast Path)

If you want to train MK's brain with minimal effort:

```bash
# 1. Launch AWS GPU instance
export AWS_KEY_NAME=your-key-pair
./aws/launch-instance.sh

# 2. SSH into the instance
ssh -i ~/.ssh/your-key.pem ubuntu@<instance-ip>

# 3. Run the all-in-one script (does everything)
git clone https://github.com/mohd2456/MK.git
bash MK/training/aws/quick-start.sh

# 4. Download the model when done
scp ubuntu@<instance-ip>:~/mk-training/output/mk-gguf/mk-brain-q4_k_m.gguf .

# 5. TERMINATE THE INSTANCE (stop paying!)
aws ec2 terminate-instances --instance-ids <instance-id>

# 6. Deploy on your i5-3470
scp mk-brain-q4_k_m.gguf user@mk-brain:/opt/mk/models/
ssh user@mk-brain "sudo bash /opt/mk/training/deploy/setup-mk-brain.sh"
```

Total time: ~2-4 hours. Total cost: ~$3-10.

---

## Directory Structure

```
training/
├── data/                      # Training dataset
│   ├── generate_dataset.py    # Hand-crafted examples (seed data)
│   ├── expand_dataset.py      # Augmentation to 786+ examples
│   ├── mk_training_data.jsonl # Full dataset (786 examples)
│   ├── mk_train.jsonl         # Training split (707 examples)
│   └── mk_val.jsonl           # Validation split (79 examples)
├── scripts/                   # Training & quantization scripts
│   ├── finetune.py            # QLoRA fine-tuning script
│   ├── quantize.py            # GGUF conversion + quantization
│   └── requirements.txt       # Python dependencies
├── aws/                       # AWS GPU instance management
│   ├── launch-instance.sh     # Spin up g5.xlarge
│   ├── setup.sh               # Install deps on instance
│   ├── train.sh               # Run the training
│   ├── quick-start.sh         # All-in-one (recommended)
│   └── terminate-instance.sh  # STOP BILLING
├── deploy/                    # Deployment to i5-3470
│   ├── setup-mk-brain.sh     # Full machine setup
│   ├── install-llama-cpp.sh   # Build llama.cpp for i5-3470
│   ├── start-llm-server.sh   # Start the LLM server
│   ├── mk-llm.service        # systemd service file
│   └── test-llm.sh           # Test the deployed model
└── README.md                  # This file
```

---

## Step-by-Step Guide

### Step 1: Prepare Training Data

The dataset is already generated (786 examples). To regenerate or modify:

```bash
cd training/data

# Edit generate_dataset.py to add/change examples
# Then regenerate:
python3 expand_dataset.py
```

**Training data categories:**
| Category | Examples | Purpose |
|----------|----------|---------|
| Intent + Tool Calling | 30 | Parse requests, pick correct tool |
| Routing Decisions | 18 | Local vs cloud decision |
| Multi-Step Planning | 10 | Break tasks into steps |
| Safety Checks | 18 | Detect dangerous operations |
| Personality | 15 | MK's communication style |
| Proactive Alerts | 8 | System event responses |
| Memory Decisions | 8 | What to remember/forget |
| Edge Cases | 10 | Ambiguous/unusual inputs |
| Generated (augmented) | 669 | Combinatorial expansions |

---

### Step 2: Launch AWS Training Instance

**Recommended: g5.xlarge**
- GPU: NVIDIA A10G (24GB VRAM)
- Cost: ~$1.01/hour
- Training time: 1-3 hours

```bash
# Set your AWS key pair name
export AWS_KEY_NAME=mk-training

# Launch (creates instance, outputs IP)
./aws/launch-instance.sh
```

Or manually via AWS Console:
1. Go to EC2 → Launch Instance
2. AMI: Deep Learning AMI (Ubuntu)
3. Instance type: g5.xlarge
4. Storage: 100GB gp3
5. Launch and note the IP

---

### Step 3: Run Training

**Option A: Quick Start (recommended)**
```bash
ssh -i ~/.ssh/mk-training.pem ubuntu@<ip>
git clone https://github.com/mohd2456/MK.git
bash MK/training/aws/quick-start.sh
```

**Option B: Manual steps**
```bash
ssh -i ~/.ssh/mk-training.pem ubuntu@<ip>

# Clone and setup
git clone https://github.com/mohd2456/MK.git
mkdir -p ~/mk-training/{data,scripts}
cp MK/training/data/*.jsonl ~/mk-training/data/
cp MK/training/scripts/*.py ~/mk-training/scripts/
cp MK/training/scripts/requirements.txt ~/mk-training/

# Install dependencies
cd ~/mk-training
bash ../MK/training/aws/setup.sh

# Run training
bash ../MK/training/aws/train.sh
```

**Training output:**
- `~/mk-training/output/mk-qwen-3b/` — LoRA adapter
- `~/mk-training/output/mk-qwen-3b-merged/` — Full merged model

---

### Step 4: Quantize

Convert the model to GGUF for llama.cpp:

```bash
# Still on the AWS instance
cd ~/mk-training
source venv/bin/activate

python scripts/quantize.py \
    --model_dir ./output/mk-qwen-3b-merged \
    --output_dir ./output/mk-gguf
```

**Output files:**
- `mk-brain-q4_k_m.gguf` — ~3.5GB (recommended for i5-3470)
- `mk-brain-q5_k_m.gguf` — ~4.5GB (higher quality if RAM allows)

---

### Step 5: Download Model & Terminate Instance

```bash
# From YOUR machine (not the AWS instance):
scp -i ~/.ssh/mk-training.pem \
    ubuntu@<ip>:~/mk-training/output/mk-gguf/mk-brain-q4_k_m.gguf \
    ./

# TERMINATE THE INSTANCE (stop paying!)
./aws/terminate-instance.sh
# Or: aws ec2 terminate-instances --instance-ids <id>
```

---

### Step 6: Deploy on i5-3470

```bash
# Copy model to the i5-3470
scp mk-brain-q4_k_m.gguf user@mk-brain:/opt/mk/models/

# SSH into the i5-3470
ssh user@mk-brain

# Run full setup (as root)
sudo bash /path/to/training/deploy/setup-mk-brain.sh

# Start the LLM server
sudo systemctl start mk-llm

# Test it
bash /path/to/training/deploy/test-llm.sh
```

**After deployment:**
- LLM API available at `http://localhost:8080`
- MK OS connects to it as a local provider
- systemd auto-restarts on crash
- Starts on boot

---

## Configuration

### Fine-Tuning Parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| Base model | Qwen2.5-3B-Instruct | Best reasoning at 3B |
| Method | QLoRA (4-bit) | Efficient, fits 24GB VRAM |
| LoRA rank | 64 | Good capacity |
| LoRA alpha | 128 | 2x rank |
| Epochs | 3 | Sufficient for 786 examples |
| Batch size | 16 (effective) | 4 per device × 4 accumulation |
| Learning rate | 2e-4 | Standard for QLoRA |
| Max seq length | 2048 | Matches deployment context |

### Deployment Parameters (i5-3470)

| Parameter | Value | Notes |
|-----------|-------|-------|
| Quantization | Q4_K_M | 3.5GB, good quality |
| Context window | 2048 tokens | Sufficient for MK tasks |
| Threads | 4 | All i5-3470 threads |
| Batch size | 512 | Prompt processing |
| Memory limit | 6GB | Leaves 2GB for OS |

---

## Costs

| Item | Cost |
|------|------|
| AWS g5.xlarge (1-3 hours) | $1-3 |
| Storage (100GB EBS) | ~$0.50 |
| Data transfer | ~$0.50 |
| **Total** | **$2-5** |

You have $300 in AWS credits. This uses about 1-2% of that.

---

## Retraining

As you use MK, it can learn from **real conversations** and retrain.

### Capture real usage (automatic, opt-in)

Set `MK_CAPTURE_CONVERSATIONS=1` to have MK record successful exchanges (from
the web UI, gateway, and WebSocket chat) to `~/.mk/training/captured.jsonl` in
the exact training format. Capture is off by default (privacy-first), only
records clean successful replies, and never logs failed/degraded answers.

```bash
# On the MK box (or in its systemd unit environment):
export MK_CAPTURE_CONVERSATIONS=1
# Optional custom location:
export MK_CAPTURE_PATH=/var/lib/mk/training/captured.jsonl
```

### Fold captured data into the dataset

```bash
python training/scripts/ingest_captured.py \
    --captured ~/.mk/training/captured.jsonl \
    --data-dir training/data
```

This de-duplicates against the existing dataset, normalizes the system prompt to
the canonical one, and appends new unique examples to `mk_train.jsonl`.

### Retrain and redeploy

1. (Optional) add hand-crafted examples to `data/generate_dataset.py` and run
   `python3 data/expand_dataset.py`
2. Spin up the AWS instance again
3. Run training (it's fast — same process)
4. Redeploy the new model

Each retrain makes MK smarter and more attuned to you.

---

## Running the local brain

Once deployed, point MK at the local model with an environment variable — it
becomes a first-class, **keyless** provider that the router prefers first (it's
free) and falls back from to the cloud only if it's unavailable:

```bash
# llama.cpp OpenAI-compatible server (default, from deploy/):
export MK_LOCAL_BRAIN_URL=http://localhost:8080/v1

# or an Ollama server:
export MK_LOCAL_BRAIN_URL=http://localhost:11434
export MK_LOCAL_BRAIN_KIND=ollama

# optional: override the served model name (default: mk-brain)
export MK_LOCAL_BRAIN_MODEL=mk-brain
```

With this set, MK runs on local inference even with **no cloud API keys at all**.

---

## Troubleshooting

**Training fails with OOM:**
- Reduce batch_size: `./train.sh --batch_size 2`
- Reduce max_seq_length: `./train.sh --max_seq_length 1024`

**Model responses are bad:**
- Add more training examples (especially for the failing category)
- Increase epochs: `./train.sh --epochs 5`
- Check the training loss curve (should decrease steadily)

**Server won't start on i5-3470:**
- Check RAM: `free -h` (need ~4GB free)
- Try smaller quant: Use `q4_k_s` instead of `q4_k_m`
- Check logs: `journalctl -u mk-llm -f`

**Slow inference:**
- Expected: 3-8 tokens/sec on i5-3470 CPU
- First request is always slower (model loading)
- Subsequent requests faster (model stays in RAM)
