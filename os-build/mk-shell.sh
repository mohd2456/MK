#!/usr/bin/env bash
#
# MK Shell - Interactive terminal interface
#
# This script replaces the default shell (bash/zsh) so that
# when a user logs in, they interact directly with MK.
# The terminal IS MK. MK IS the terminal.
#
# If MK is not running, falls back to a minimal recovery shell.

set -euo pipefail

MK_BIN="/usr/bin/python3"
MK_MODULE="mk.main"
MK_HOME="/opt/mk"

# Show MOTD
if [ -f /etc/motd ]; then
    cat /etc/motd
fi

# Check if MK is available
if [ -f "$MK_HOME/pyproject.toml" ] && command -v "$MK_BIN" &>/dev/null; then
    # Start MK in interactive terminal mode
    cd "$MK_HOME"
    exec "$MK_BIN" -m "$MK_MODULE" --mode terminal
else
    # Fallback: minimal recovery shell
    echo ""
    echo "[MK] System not fully initialized. Entering recovery mode."
    echo "[MK] Run 'mk-setup' to complete installation."
    echo ""
    exec /bin/bash --login
fi
