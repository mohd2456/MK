#!/usr/bin/env bash
#
# MK Deploy — Start the local LLM server
#
# Starts llama.cpp server with the MK brain model.
# Configured for i5-3470 (8GB RAM, no GPU).
#
# Usage:
#   ./start-llm-server.sh
#   ./start-llm-server.sh --model /path/to/other-model.gguf
#

set -euo pipefail

# Configuration
MODEL_DIR="/opt/mk/models"
MODEL_FILE="${MODEL_FILE:-$MODEL_DIR/mk-brain-q4_k_m.gguf}"
HOST="0.0.0.0"
PORT="8080"
CONTEXT_SIZE="2048"      # Context window (tokens)
THREADS="4"              # i5-3470 has 4 threads
BATCH_SIZE="512"         # Batch size for prompt processing
PARALLEL="1"             # Number of parallel requests (keep at 1 for 8GB RAM)

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        --model) MODEL_FILE="$2"; shift 2 ;;
        --port) PORT="$2"; shift 2 ;;
        --context) CONTEXT_SIZE="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Verify model exists
if [ ! -f "$MODEL_FILE" ]; then
    echo "[ERROR] Model not found: $MODEL_FILE"
    echo ""
    echo "Place your quantized model at: $MODEL_DIR/mk-brain-q4_k_m.gguf"
    echo ""
    echo "Download from AWS training instance:"
    echo "  scp user@aws-instance:~/mk-training/output/mk-gguf/mk-brain-q4_k_m.gguf $MODEL_DIR/"
    exit 1
fi

MODEL_SIZE=$(du -h "$MODEL_FILE" | cut -f1)

echo "=============================================="
echo "  MK Brain — Starting LLM Server"
echo "=============================================="
echo ""
echo "  Model:    $MODEL_FILE ($MODEL_SIZE)"
echo "  Host:     $HOST:$PORT"
echo "  Context:  $CONTEXT_SIZE tokens"
echo "  Threads:  $THREADS"
echo "  Batch:    $BATCH_SIZE"
echo ""
echo "  API endpoint: http://localhost:$PORT"
echo "  Health check: http://localhost:$PORT/health"
echo ""
echo "  Press Ctrl+C to stop"
echo "=============================================="
echo ""

# Start the server
exec mk-llm-server \
    --model "$MODEL_FILE" \
    --host "$HOST" \
    --port "$PORT" \
    --ctx-size "$CONTEXT_SIZE" \
    --threads "$THREADS" \
    --batch-size "$BATCH_SIZE" \
    --parallel "$PARALLEL" \
    --cont-batching \
    --mlock \
    --log-disable
