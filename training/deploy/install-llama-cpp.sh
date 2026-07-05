#!/usr/bin/env bash
#
# MK Deploy — Install llama.cpp on the i5-3470
#
# Builds llama.cpp from source optimized for the i5-3470 CPU.
# The i5-3470 supports AVX but NOT AVX2, so we compile accordingly.
#
# Usage:
#   chmod +x install-llama-cpp.sh
#   ./install-llama-cpp.sh
#

set -euo pipefail

echo "=============================================="
echo "  MK — Installing llama.cpp"
echo "=============================================="
echo ""

# Install build dependencies
echo "[1/4] Installing build dependencies..."
if command -v apt-get &>/dev/null; then
    sudo apt-get update -qq
    sudo apt-get install -y -qq build-essential cmake git
elif command -v dnf &>/dev/null; then
    sudo dnf install -y -q gcc gcc-c++ cmake git make
elif command -v pacman &>/dev/null; then
    sudo pacman -S --noconfirm base-devel cmake git
fi

# Clone llama.cpp
INSTALL_DIR="/opt/llama.cpp"
echo "[2/4] Cloning llama.cpp..."
if [ -d "$INSTALL_DIR" ]; then
    echo "  Updating existing installation..."
    cd "$INSTALL_DIR"
    sudo git pull --depth 1
else
    sudo git clone --depth 1 https://github.com/ggerganov/llama.cpp.git "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# Build optimized for i5-3470 (Ivy Bridge — has AVX but NOT AVX2)
echo "[3/4] Building llama.cpp (optimized for i5-3470)..."
sudo mkdir -p build
cd build

# i5-3470 is Ivy Bridge (march=ivybridge includes SSE4.2 + AVX)
sudo cmake .. \
    -DCMAKE_BUILD_TYPE=Release \
    -DGGML_CUDA=OFF \
    -DGGML_AVX2=OFF \
    -DCMAKE_C_FLAGS="-march=ivybridge" \
    -DCMAKE_CXX_FLAGS="-march=ivybridge"

sudo cmake --build . --config Release -j$(nproc)

# Create symlinks
echo "[4/4] Creating symlinks..."
sudo ln -sf "$INSTALL_DIR/build/bin/llama-server" /usr/local/bin/mk-llm-server
sudo ln -sf "$INSTALL_DIR/build/bin/llama-cli" /usr/local/bin/mk-llm-cli

echo ""
echo "=============================================="
echo "  llama.cpp installed!"
echo "=============================================="
echo ""
echo "  Binary: /usr/local/bin/mk-llm-server"
echo "  CLI:    /usr/local/bin/mk-llm-cli"
echo ""
echo "  Test with:"
echo "    mk-llm-server --version"
echo ""
echo "  Next: Place your model at /opt/mk/models/mk-brain-q4_k_m.gguf"
echo "        Then run: ./start-llm-server.sh"
echo ""
