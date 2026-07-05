#!/usr/bin/env bash
#
# MK OS Build Script
# Creates a minimal Linux image that boots directly into MK.
#
# The image contains:
# - Linux kernel with minimal modules
# - Networking (systemd-networkd + DHCP)
# - Python 3.9+ runtime
# - Node.js 22 runtime
# - MK AI Operating System
#
# Usage:
#   ./build.sh [--output DIR] [--arch ARCH]
#
# Requirements:
#   - Docker (for reproducible builds)
#   - OR: debootstrap, squashfs-tools, xorriso (for native builds)
#
# The resulting image boots directly into MK terminal mode.
# No GUI. No desktop. No bloat. Just MK.

set -euo pipefail

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="${OUTPUT_DIR:-$SCRIPT_DIR/output}"
BUILD_DIR="${BUILD_DIR:-$SCRIPT_DIR/.build}"
ARCH="${ARCH:-amd64}"
IMAGE_NAME="mk-os"
IMAGE_VERSION="0.1.0"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --arch)
            ARCH="$2"
            shift 2
            ;;
        --help)
            echo "MK OS Build Script"
            echo ""
            echo "Usage: ./build.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --output DIR   Output directory (default: ./output)"
            echo "  --arch ARCH    Target architecture (default: amd64)"
            echo "  --help         Show this help message"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    if command -v docker &>/dev/null; then
        log_success "Docker found - will use containerized build"
        BUILD_METHOD="docker"
    elif command -v debootstrap &>/dev/null; then
        log_success "debootstrap found - will use native build"
        BUILD_METHOD="native"
    else
        log_error "Neither Docker nor debootstrap found."
        log_error "Install Docker for containerized builds, or debootstrap for native builds."
        exit 1
    fi
}

# Create the rootfs using debootstrap (Alpine-based for minimal size)
create_rootfs() {
    log_info "Creating minimal rootfs..."

    mkdir -p "$BUILD_DIR/rootfs"

    if [ "$BUILD_METHOD" = "docker" ]; then
        log_info "Building rootfs via Docker..."
        docker build -t "$IMAGE_NAME-builder" -f "$SCRIPT_DIR/Dockerfile" "$PROJECT_ROOT"
        docker create --name "$IMAGE_NAME-extract" "$IMAGE_NAME-builder" /bin/true
        docker export "$IMAGE_NAME-extract" | tar -C "$BUILD_DIR/rootfs" -xf -
        docker rm "$IMAGE_NAME-extract"
    else
        log_info "Building rootfs via debootstrap..."
        sudo debootstrap --arch="$ARCH" --variant=minbase \
            bookworm "$BUILD_DIR/rootfs" http://deb.debian.org/debian
    fi

    log_success "Rootfs created"
}

# Install MK into the rootfs
install_mk() {
    log_info "Installing MK into rootfs..."

    local rootfs="$BUILD_DIR/rootfs"

    # Copy MK source
    mkdir -p "$rootfs/opt/mk"
    cp -r "$PROJECT_ROOT/src" "$rootfs/opt/mk/"
    cp -r "$PROJECT_ROOT/gateway" "$rootfs/opt/mk/"
    cp "$PROJECT_ROOT/pyproject.toml" "$rootfs/opt/mk/"

    # Copy service files
    mkdir -p "$rootfs/etc/systemd/system"
    cp "$SCRIPT_DIR/mk.service" "$rootfs/etc/systemd/system/"

    # Copy MOTD
    cp "$SCRIPT_DIR/motd" "$rootfs/etc/motd"

    # Copy shell wrapper
    mkdir -p "$rootfs/usr/local/bin"
    cp "$SCRIPT_DIR/mk-shell.sh" "$rootfs/usr/local/bin/mk-shell"
    chmod +x "$rootfs/usr/local/bin/mk-shell"

    log_success "MK installed into rootfs"
}

# Configure the system
configure_system() {
    log_info "Configuring system..."

    local rootfs="$BUILD_DIR/rootfs"

    # Set hostname
    echo "mk" > "$rootfs/etc/hostname"

    # Configure networking (DHCP on all interfaces)
    mkdir -p "$rootfs/etc/systemd/network"
    cat > "$rootfs/etc/systemd/network/80-dhcp.network" << 'EOF'
[Match]
Name=en* eth*

[Network]
DHCP=yes
EOF

    # Set MK shell as default for root
    if [ -f "$rootfs/etc/passwd" ]; then
        sed -i 's|root:x:0:0:root:/root:/bin/bash|root:x:0:0:root:/root:/usr/local/bin/mk-shell|' \
            "$rootfs/etc/passwd" 2>/dev/null || true
    fi

    # Enable services
    mkdir -p "$rootfs/etc/systemd/system/multi-user.target.wants"
    ln -sf /etc/systemd/system/mk.service \
        "$rootfs/etc/systemd/system/multi-user.target.wants/mk.service" 2>/dev/null || true

    log_success "System configured"
}

# Create the final image
create_image() {
    log_info "Creating bootable image..."

    mkdir -p "$OUTPUT_DIR"

    # For now, create a tar archive of the rootfs
    # A full ISO/disk image requires additional tooling
    local output_file="$OUTPUT_DIR/${IMAGE_NAME}-${IMAGE_VERSION}-${ARCH}.tar.gz"

    tar -czf "$output_file" -C "$BUILD_DIR/rootfs" .

    log_success "Image created: $output_file"
    log_info "Image size: $(du -h "$output_file" | cut -f1)"
}

# Cleanup build artifacts
cleanup() {
    log_info "Cleaning up build directory..."
    rm -rf "$BUILD_DIR"
    log_success "Cleanup complete"
}

# Main build sequence
main() {
    echo ""
    echo "  ███╗   ███╗██╗  ██╗     ██████╗ ███████╗"
    echo "  ████╗ ████║██║ ██╔╝    ██╔═══██╗██╔════╝"
    echo "  ██╔████╔██║█████╔╝     ██║   ██║███████╗"
    echo "  ██║╚██╔╝██║██╔═██╗     ██║   ██║╚════██║"
    echo "  ██║ ╚═╝ ██║██║  ██╗    ╚██████╔╝███████║"
    echo "  ╚═╝     ╚═╝╚═╝  ╚═╝     ╚═════╝ ╚══════╝"
    echo ""
    echo "  Building MK OS v${IMAGE_VERSION} for ${ARCH}"
    echo ""

    check_prerequisites
    create_rootfs
    install_mk
    configure_system
    create_image
    cleanup

    echo ""
    log_success "MK OS build complete!"
    log_info "Output: $OUTPUT_DIR/"
    echo ""
}

main "$@"
