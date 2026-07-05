#!/usr/bin/env bash
#
# MK Deploy — Full Setup for i5-3470 (MK Brain Machine)
#
# This script sets up everything needed to run MK's local LLM
# on the i5-3470 desktop with 8GB RAM and custom minimal Linux.
#
# What it does:
#   1. Creates mk user and directories
#   2. Installs llama.cpp (built for i5-3470)
#   3. Sets up systemd service
#   4. Configures the LLM server
#   5. Verifies everything works
#
# Usage:
#   chmod +x setup-mk-brain.sh
#   sudo ./setup-mk-brain.sh
#
# After setup:
#   - Place model at /opt/mk/models/mk-brain-q4_k_m.gguf
#   - Start: sudo systemctl start mk-llm
#   - MK API at: http://localhost:8080
#

set -euo pipefail

# Must run as root
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root: sudo ./setup-mk-brain.sh"
    exit 1
fi

echo ""
echo "  ███╗   ███╗██╗  ██╗    ██████╗ ██████╗  █████╗ ██╗███╗   ██╗"
echo "  ████╗ ████║██║ ██╔╝    ██╔══██╗██╔══██╗██╔══██╗██║████╗  ██║"
echo "  ██╔████╔██║█████╔╝     ██████╔╝██████╔╝███████║██║██╔██╗ ██║"
echo "  ██║╚██╔╝██║██╔═██╗     ██╔══██╗██╔══██╗██╔══██║██║██║╚██╗██║"
echo "  ██║ ╚═╝ ██║██║  ██╗    ██████╔╝██║  ██║██║  ██║██║██║ ╚████║"
echo "  ╚═╝     ╚═╝╚═╝  ╚═╝    ╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚═╝ ╚═══╝"
echo ""
echo "  Setting up MK Brain on i5-3470"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Step 1: Create mk user and directories
echo "[1/5] Creating mk user and directories..."
if ! id "mk" &>/dev/null; then
    useradd -r -s /bin/false -d /opt/mk mk
fi

mkdir -p /opt/mk/{models,config,logs,data}
chown -R mk:mk /opt/mk

echo "  User: mk"
echo "  Home: /opt/mk"
echo "  Models: /opt/mk/models/"

# Step 2: Install llama.cpp
echo ""
echo "[2/5] Installing llama.cpp..."
bash "$SCRIPT_DIR/install-llama-cpp.sh"

# Step 3: Install systemd service
echo ""
echo "[3/5] Installing systemd service..."
cp "$SCRIPT_DIR/mk-llm.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable mk-llm

echo "  Service: mk-llm (enabled, not started yet)"

# Step 4: Create MK config for LLM connection
echo ""
echo "[4/5] Creating MK LLM configuration..."
cat > /opt/mk/config/llm-local.yaml << 'EOF'
# MK Local LLM Configuration
# This connects MK OS to its local brain (llama.cpp server)

provider:
  name: "mk-brain"
  type: "openai_compatible"
  endpoint: "http://127.0.0.1:8080"
  model: "mk-brain-q4_k_m"
  api_key: "not-needed"  # Local server doesn't need auth

# Performance settings for i5-3470
inference:
  max_tokens: 512          # Keep responses concise (MK style)
  temperature: 0.3         # Low temp = more deterministic decisions
  top_p: 0.9
  repeat_penalty: 1.1

# Context settings
context:
  max_context: 2048        # Match server context size
  system_prompt_budget: 800  # Tokens reserved for system prompt
  memory_budget: 600       # Tokens for memory context
  user_budget: 650         # Remaining for user input + response
EOF

chown mk:mk /opt/mk/config/llm-local.yaml

echo "  Config: /opt/mk/config/llm-local.yaml"

# Step 5: Verify setup
echo ""
echo "[5/5] Verifying setup..."

# Check llama.cpp binary
if command -v mk-llm-server &>/dev/null; then
    echo "  [OK] mk-llm-server binary found"
else
    echo "  [WARN] mk-llm-server not found in PATH"
fi

# Check directories
if [ -d "/opt/mk/models" ]; then
    echo "  [OK] Model directory exists: /opt/mk/models/"
else
    echo "  [WARN] Model directory missing"
fi

# Check service
if systemctl is-enabled mk-llm &>/dev/null; then
    echo "  [OK] mk-llm service enabled"
else
    echo "  [WARN] mk-llm service not enabled"
fi

# Check for model file
if [ -f "/opt/mk/models/mk-brain-q4_k_m.gguf" ]; then
    MODEL_SIZE=$(du -h /opt/mk/models/mk-brain-q4_k_m.gguf | cut -f1)
    echo "  [OK] Model found ($MODEL_SIZE)"
    echo ""
    echo "  Ready to start! Run:"
    echo "    sudo systemctl start mk-llm"
else
    echo "  [--] Model not found yet"
    echo ""
    echo "  Place your model at: /opt/mk/models/mk-brain-q4_k_m.gguf"
    echo ""
    echo "  Copy from training machine:"
    echo "    scp user@training-machine:~/mk-training/output/mk-gguf/mk-brain-q4_k_m.gguf /opt/mk/models/"
    echo ""
    echo "  Then start:"
    echo "    sudo systemctl start mk-llm"
fi

echo ""
echo "=============================================="
echo "  Setup complete!"
echo "=============================================="
echo ""
echo "  Test the LLM (after placing model + starting service):"
echo "    curl http://localhost:8080/v1/chat/completions \\"
echo "      -H 'Content-Type: application/json' \\"
echo "      -d '{"
echo "        \"model\": \"mk-brain\","
echo "        \"messages\": [{\"role\": \"user\", \"content\": \"check server status\"}]"
echo "      }'"
echo ""
echo "  Monitor:"
echo "    sudo systemctl status mk-llm"
echo "    journalctl -u mk-llm -f"
echo ""
