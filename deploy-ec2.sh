#!/bin/bash
#
# MK OS — AWS CloudShell Deployment Script
# ==========================================
# Paste this ENTIRE script into AWS CloudShell.
# It will:
#   1. Create a key pair
#   2. Create a security group
#   3. Launch a Debian 12 EC2 instance
#   4. Wait for it to boot
#   5. SSH in and install MK OS
#   6. Connect to Tailscale
#   7. Remove SSH access (Tailscale replaces it)
#
# BEFORE RUNNING: Set your Tailscale auth key below
# Get it from: https://login.tailscale.com/admin/settings/keys
#

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION — EDIT THESE
# ═══════════════════════════════════════════════════════════════

TAILSCALE_AUTH_KEY=""   # <-- PASTE YOUR tskey-auth-xxx HERE
INSTANCE_TYPE="t3.small"
REGION="us-east-1"
NAME="mk-brain"
DISK_SIZE=30

# ═══════════════════════════════════════════════════════════════
# DO NOT EDIT BELOW THIS LINE
# ═══════════════════════════════════════════════════════════════

set -e

echo "╔══════════════════════════════════════════╗"
echo "║       MK OS — EC2 Deployment            ║"
echo "╚══════════════════════════════════════════╝"
echo ""

if [ -z "$TAILSCALE_AUTH_KEY" ]; then
  echo "ERROR: Set TAILSCALE_AUTH_KEY at the top of this script"
  echo "Get one from: https://login.tailscale.com/admin/settings/keys"
  echo "(Reusable, Pre-approved, No expiry)"
  exit 1
fi

export AWS_DEFAULT_REGION=$REGION

# ─── Step 1: Key Pair ───
echo "[1/7] Creating SSH key pair..."
KEY_NAME="mk-deploy-key-$(date +%s)"
aws ec2 create-key-pair \
  --key-name "$KEY_NAME" \
  --query 'KeyMaterial' \
  --output text > /tmp/$KEY_NAME.pem
chmod 400 /tmp/$KEY_NAME.pem
echo "  ✓ Key: $KEY_NAME"

# ─── Step 2: Security Group ───
echo "[2/7] Creating security group..."
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query 'Vpcs[0].VpcId' --output text)
SG_ID=$(aws ec2 create-security-group \
  --group-name "mk-deploy-sg-$(date +%s)" \
  --description "MK OS temp SSH access" \
  --vpc-id "$VPC_ID" \
  --query 'GroupId' --output text)
aws ec2 authorize-security-group-ingress \
  --group-id "$SG_ID" \
  --protocol tcp --port 22 --cidr 0.0.0.0/0 > /dev/null
echo "  ✓ Security group: $SG_ID"

# ─── Step 3: Find Debian 12 AMI ───
echo "[3/7] Finding Debian 12 AMI..."
AMI_ID=$(aws ec2 describe-images \
  --owners 136693071363 \
  --filters "Name=name,Values=debian-12-amd64-*" "Name=state,Values=available" \
  --query 'sort_by(Images, &CreationDate)[-1].ImageId' \
  --output text)
echo "  ✓ AMI: $AMI_ID"

# ─── Step 4: Launch Instance ───
echo "[4/7] Launching EC2 instance ($INSTANCE_TYPE)..."
INSTANCE_ID=$(aws ec2 run-instances \
  --image-id "$AMI_ID" \
  --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY_NAME" \
  --security-group-ids "$SG_ID" \
  --block-device-mappings "[{\"DeviceName\":\"/dev/xvda\",\"Ebs\":{\"VolumeSize\":$DISK_SIZE,\"VolumeType\":\"gp3\"}}]" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NAME}]" \
  --query 'Instances[0].InstanceId' \
  --output text)
echo "  ✓ Instance: $INSTANCE_ID"
echo "  Waiting for instance to be running..."
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"

# Get public IP
PUBLIC_IP=$(aws ec2 describe-instances \
  --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text)
echo "  ✓ Public IP: $PUBLIC_IP"

# ─── Step 5: Wait for SSH ───
echo "[5/7] Waiting for SSH to be ready..."
for i in $(seq 1 30); do
  if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -i /tmp/$KEY_NAME.pem admin@$PUBLIC_IP "echo ready" 2>/dev/null; then
    break
  fi
  sleep 5
done
echo "  ✓ SSH ready"

# ─── Step 6: Install MK OS ───
echo "[6/7] Installing MK OS (this takes 2-3 minutes)..."
ssh -o StrictHostKeyChecking=no -i /tmp/$KEY_NAME.pem admin@$PUBLIC_IP "TAILSCALE_AUTH_KEY='$TAILSCALE_AUTH_KEY' bash -s" << 'INSTALL_SCRIPT'
#!/bin/bash
set -e

echo ">>> Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip python3-venv git curl ca-certificates gnupg

echo ">>> Installing Node.js 22..."
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo bash -
sudo apt-get install -y -qq nodejs
sudo npm install -g pnpm

echo ">>> Installing Tailscale..."
curl -fsSL https://tailscale.com/install.sh | sudo sh

echo ">>> Cloning MK OS..."
sudo git clone https://github.com/mohd2456/MK.git /opt/mk
cd /opt/mk

echo ">>> Installing Python package..."
sudo pip3 install --break-system-packages .

echo ">>> Building Web UI..."
cd /opt/mk/webui
sudo pnpm install --no-frozen-lockfile
sudo pnpm build
cd /opt/mk

echo ">>> Installing Gateway..."
cd /opt/mk/gateway
sudo pnpm install --no-frozen-lockfile || true
cd /opt/mk

echo ">>> Setting up system..."
sudo mkdir -p /etc/mk ~/.mk/plugins ~/.mk/memory ~/.mk/snapshots
sudo cp os-build/mk.service /etc/systemd/system/
sudo cp os-build/mk-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tailscaled
sudo systemctl enable --now mk-web.service

echo ">>> Connecting to Tailscale..."
sudo tailscale up --auth-key=$TAILSCALE_AUTH_KEY --hostname=mk-brain --ssh --accept-routes

echo ""
echo "════════════════════════════════════════════"
echo "  MK OS INSTALLED SUCCESSFULLY"
echo "════════════════════════════════════════════"
echo "  Tailscale IP: $(tailscale ip -4)"
echo "  Web UI: http://$(tailscale ip -4):8080"
echo "  Hostname: mk-brain"
echo "  PIN: 5610"
echo "  SSH: ssh admin@mk-brain (via Tailscale)"
echo "════════════════════════════════════════════"
INSTALL_SCRIPT

# ─── Step 7: Lock down security ───
echo "[7/7] Removing public SSH access (Tailscale replaces it)..."
aws ec2 revoke-security-group-ingress \
  --group-id "$SG_ID" \
  --protocol tcp --port 22 --cidr 0.0.0.0/0 2>/dev/null || true
echo "  ✓ Port 22 closed — use Tailscale SSH from now on"

# ─── Done ───
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║         MK OS — DEPLOYED ✓              ║"
echo "╠══════════════════════════════════════════╣"
echo "║                                          ║"
echo "║  Web UI:  http://mk-brain:8080           ║"
echo "║  PIN:     5610                           ║"
echo "║  SSH:     ssh admin@mk-brain             ║"
echo "║                                          ║"
echo "║  (Access from any device on your         ║"
echo "║   Tailscale network)                     ║"
echo "║                                          ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "Instance ID: $INSTANCE_ID"
echo "Key file: /tmp/$KEY_NAME.pem (delete after confirming Tailscale works)"
echo ""
echo "To destroy: aws ec2 terminate-instances --instance-ids $INSTANCE_ID"
