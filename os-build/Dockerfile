# MK OS Build Environment
#
# Creates a minimal Linux filesystem containing only
# what MK needs to run. Used for reproducible OS builds.
#
# Build: docker build -t mk-os-builder -f os-build/Dockerfile .
# Extract: docker create --name mk-extract mk-os-builder && docker export mk-extract > rootfs.tar

FROM debian:bookworm-slim AS base

# Install only essential packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    systemd \
    systemd-sysv \
    networkd-dispatcher \
    iproute2 \
    iputils-ping \
    curl \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install Tailscale
RUN curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.noarmor.gpg \
    | tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null \
    && curl -fsSL https://pkgs.tailscale.com/stable/debian/bookworm.tailscale-keyring.list \
    | tee /etc/apt/sources.list.d/tailscale.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends tailscale \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install Node.js 22 (for gateway)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g pnpm

# Create MK directories
RUN mkdir -p /opt/mk /var/lib/mk /var/log/mk /etc/mk

# Copy MK source
COPY src/ /opt/mk/src/
COPY pyproject.toml /opt/mk/
COPY gateway/ /opt/mk/gateway/

# Install MK Python dependencies
WORKDIR /opt/mk
RUN python3 -m pip install --break-system-packages --no-cache-dir .

# Install gateway dependencies
WORKDIR /opt/mk/gateway
RUN pnpm install --prod && pnpm build || true

# Copy system configuration
COPY os-build/mk.service /etc/systemd/system/mk.service
COPY os-build/motd /etc/motd
COPY os-build/mk-shell.sh /usr/local/bin/mk-shell
RUN chmod +x /usr/local/bin/mk-shell

# Set hostname
RUN echo "mk" > /etc/hostname

# Enable MK service
RUN systemctl enable mk.service 2>/dev/null || \
    ln -sf /etc/systemd/system/mk.service \
    /etc/systemd/system/multi-user.target.wants/mk.service

WORKDIR /opt/mk
CMD ["/usr/bin/python3", "-m", "mk.main", "--mode", "daemon"]
