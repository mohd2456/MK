#!/usr/bin/env bash
#
# MK OS Installer
#
# Runs on a fresh server install. Supported distributions:
#   - Debian 12 (Bookworm) / Ubuntu           (apt)
#   - Amazon Linux 2023 / Fedora / RHEL / CentOS (dnf/yum)
#
# When done, reboot. You'll see MK immediately — no login screen.
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/mohd2456/MK/main/os-build/install.sh | sudo bash
#
# Or:
#   git clone https://github.com/mohd2456/MK.git /opt/mk
#   cd /opt/mk && sudo bash os-build/install.sh
#

set -euo pipefail

# --- Config ---
MK_USER="mk"
MK_HOME="/opt/mk"
MK_DATA="/var/lib/mk"
MK_CONFIG="/etc/mk"
MK_LOG="/var/log/mk"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[MK]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail()  { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }

# --- Pre-checks ---
if [ "$(id -u)" -ne 0 ]; then
    fail "Run as root: sudo bash install.sh"
fi

# --- Distro detection ---
# Determine the package-manager family so the rest of the installer can pick
# the right package names. PKG_FAMILY is "debian" (apt) or "rhel" (dnf/yum).
PKG_FAMILY=""
PKG_MGR=""
DISTRO_ID="unknown"
if [ -r /etc/os-release ]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    DISTRO_ID="${ID:-unknown}"
fi

if command -v apt-get &>/dev/null; then
    PKG_FAMILY="debian"
    PKG_MGR="apt-get"
elif command -v dnf &>/dev/null; then
    PKG_FAMILY="rhel"
    PKG_MGR="dnf"
elif command -v yum &>/dev/null; then
    PKG_FAMILY="rhel"
    PKG_MGR="yum"
else
    fail "Unsupported distro: could not find apt-get, dnf, or yum."
fi

info "Installing MK OS on $(hostname) (distro: ${DISTRO_ID}, package manager: ${PKG_MGR})..."
echo ""

# --- Package helpers (distro-agnostic) ---
pkg_refresh() {
    case "$PKG_FAMILY" in
        debian) apt-get update -qq ;;
        rhel)   "$PKG_MGR" makecache -q >/dev/null 2>&1 || true ;;
    esac
}

# Install packages, tolerating any that are unavailable on this distro
# (mirrors the original best-effort behavior for optional homelab tooling).
pkg_install() {
    case "$PKG_FAMILY" in
        debian) apt-get install -y -qq "$@" >/dev/null 2>&1 || true ;;
        rhel)   "$PKG_MGR" install -y -q "$@" >/dev/null 2>&1 || true ;;
    esac
}

# --- 1. System packages ---
info "Installing system packages..."
pkg_refresh

if [ "$PKG_FAMILY" = "debian" ]; then
    pkg_install \
        python3 python3-pip python3-venv python3-dev \
        git curl wget \
        zfsutils-linux \
        docker.io docker-compose-plugin \
        nftables wireguard-tools \
        smartmontools lm-sensors \
        eject ffmpeg \
        iproute2 iputils-ping dnsutils nmap \
        sudo systemd \
        libvirt-daemon-system virtinst qemu-kvm \
        lxc lxc-templates \
        ethtool
else
    # RHEL family (Amazon Linux 2023, Fedora, RHEL, CentOS Stream).
    # EPEL broadens availability of tools like nmap on RHEL/CentOS; it is a
    # no-op / harmless failure on Amazon Linux 2023 and Fedora.
    "$PKG_MGR" install -y -q epel-release >/dev/null 2>&1 || true
    pkg_install \
        python3 python3-pip python3-devel \
        git curl wget \
        nftables wireguard-tools \
        smartmontools lm_sensors \
        eject ffmpeg \
        iproute iputils bind-utils nmap \
        sudo systemd \
        libvirt virt-install qemu-kvm \
        lxc \
        ethtool
    # Docker: package is "docker" on Amazon Linux 2023; the Compose plugin is
    # not always packaged, so install what exists and note the rest.
    pkg_install docker
    if ! command -v docker &>/dev/null; then
        warn "Docker was not installed automatically. Install it per your distro's docs."
    fi
    # ZFS is not in RHEL-family base repos (needs OpenZFS/kmod setup). Attempt
    # the common package name but continue without it if unavailable.
    pkg_install zfs || true
    if ! command -v zpool &>/dev/null; then
        warn "ZFS tools not installed (not in base repos on this distro). See https://openzfs.github.io/openzfs-docs/ for setup; storage features will be limited."
    fi
fi
ok "System packages installed"

# --- 2. Install MakeMKV (disc ripper) ---
info "Installing MakeMKV..."
if ! command -v makemkvcon &>/dev/null; then
    if [ "$PKG_FAMILY" = "debian" ]; then
        # Build dependencies for a manual MakeMKV build
        pkg_install \
            build-essential pkg-config libc6-dev libssl-dev libexpat1-dev \
            libavcodec-dev libgl1-mesa-dev qtbase5-dev zlib1g-dev
    else
        # RHEL family build dependencies
        "$PKG_MGR" groupinstall -y -q "Development Tools" >/dev/null 2>&1 || true
        pkg_install \
            pkgconf-pkg-config openssl-devel expat-devel \
            ffmpeg-devel mesa-libGL-devel qt5-qtbase-devel zlib-devel
    fi
    echo "NOTE: MakeMKV needs a manual install from https://www.makemkv.com/forum/viewtopic.php?t=224"
fi
ok "MakeMKV check done"

# --- 3. Install MK ---
info "Installing MK..."
if [ ! -d "$MK_HOME/.git" ]; then
    if [ -d "/opt/mk/src" ]; then
        # Already cloned (running from repo)
        MK_HOME="/opt/mk"
    else
        git clone https://github.com/mohd2456/MK.git "$MK_HOME"
    fi
fi

cd "$MK_HOME"
# Newer distros (Debian 12+, Fedora) mark the system Python as
# externally-managed (PEP 668) and require --break-system-packages for a
# system-wide pip install. Older ones reject the unknown flag, so fall back.
if pip3 install --break-system-packages -e . > /dev/null 2>&1; then
    :
else
    pip3 install -e . > /dev/null 2>&1
fi
ok "MK installed"

# --- 4. Create directories ---
info "Creating MK directories..."
mkdir -p "$MK_DATA" "$MK_CONFIG" "$MK_LOG"
mkdir -p /etc/mk/backups /var/lib/mk/backups
mkdir -p /opt/mk/stacks
mkdir -p /media/movies /media/tv
ok "Directories created"

# --- 5. Create MK config ---
info "Creating default config..."
if [ ! -f "$MK_CONFIG/config.yaml" ]; then
    cat > "$MK_CONFIG/config.yaml" << 'EOF'
# MK OS Configuration
# Add your LLM provider API key to enable AI features

llm_providers: []
#  - name: claude
#    api_key_ref: ANTHROPIC_API_KEY
#    model: claude-sonnet-4-6
#    endpoint: https://api.anthropic.com
#    priority: 10
#    max_tokens: 4096

machines: []
services: []

memory:
  short_term_max_messages: 50
  long_term_storage_path: /var/lib/mk/memory
  context_window_budget: 8000

safety:
  confirm_destructive: true
  audit_log_path: /var/log/mk/audit.log
  max_iterations: 10

telegram:
  enabled: false
EOF
fi
ok "Config created at $MK_CONFIG/config.yaml"

# --- 6. Create MK systemd service ---
info "Creating systemd service..."
cat > /etc/systemd/system/mk.service << EOF
[Unit]
Description=MK AI Operating System
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=$MK_HOME
ExecStart=/usr/bin/python3 -m mk.main --mode daemon --config $MK_CONFIG/config.yaml
Restart=always
RestartSec=5
Environment=MK_HOME=$MK_HOME
Environment=MK_CONFIG=$MK_CONFIG/config.yaml
Environment=MK_DATA=$MK_DATA
Environment=MK_LOG=$MK_LOG
StandardOutput=journal
StandardError=journal
SyslogIdentifier=mk

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable mk.service
ok "MK service enabled"

# --- 7. Set up auto-login + MK as shell on tty1 ---
info "Configuring auto-login to MK on console..."

# Create the MK shell wrapper
cat > /usr/local/bin/mk-shell << 'SHELL'
#!/usr/bin/env bash
# MK Shell — what you see when you log in
cd /opt/mk
exec /usr/bin/python3 -m mk.main --mode terminal --config /etc/mk/config.yaml
SHELL
chmod +x /usr/local/bin/mk-shell

# Auto-login on tty1 (no username/password prompt)
mkdir -p /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf << 'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin root --noclear %I $TERM
EOF

# Set MK as root's login shell on tty1 via .bash_profile
# (Only on tty1, SSH still gives normal bash)
cat > /root/.bash_profile << 'EOF'
# If on tty1 (console), launch MK directly
if [ "$(tty)" = "/dev/tty1" ]; then
    exec /usr/local/bin/mk-shell
fi
EOF

ok "Console auto-login configured (tty1 → MK)"

# --- 8. Set MOTD ---
info "Setting MOTD..."
cat > /etc/motd << 'EOF'

  ███╗   ███╗██╗  ██╗
  ████╗ ████║██║ ██╔╝
  ██╔████╔██║█████╔╝
  ██║╚██╔╝██║██╔═██╗
  ██║ ╚═╝ ██║██║  ██╗
  ╚═╝     ╚═╝╚═╝  ╚═╝

  MK OS — Personal AI Operating System

EOF
ok "MOTD set"

# --- 9. Enable Docker for root ---
info "Configuring Docker..."
systemctl enable docker
systemctl start docker || true
ok "Docker enabled"

# --- 10. Set hostname ---
info "Setting hostname to 'mk'..."
hostnamectl set-hostname mk
echo "mk" > /etc/hostname
ok "Hostname set"

# --- Done ---
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo -e "  ${GREEN}MK OS installed successfully.${NC}"
echo ""
echo "  What happens on reboot:"
echo "    1. Machine powers on"
echo "    2. Auto-logs in (no password prompt)"
echo "    3. MK boot sequence runs"
echo "    4. You see MK> prompt"
echo "    5. Just talk."
echo ""
echo "  SSH still works normally (gives you bash)."
echo "  To configure AI: edit /etc/mk/config.yaml"
echo "  To see logs: journalctl -u mk"
echo ""
echo "  Reboot now:  sudo reboot"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
