#!/usr/bin/env bash
#
# MK Training — Launch AWS GPU Instance
#
# This script launches a g5.xlarge GPU instance on AWS for training.
# Requires: AWS CLI configured with your credentials.
#
# Usage:
#   ./launch-instance.sh
#
# IMPORTANT: Remember to terminate the instance when done!
#   aws ec2 terminate-instances --instance-ids <instance-id>
#
# Cost: ~$1.01/hour for g5.xlarge (A10G 24GB)
# Expected training time: 1-3 hours
# Expected total cost: $3-10
#

set -euo pipefail

echo "=============================================="
echo "  MK Training — Launch AWS GPU Instance"
echo "=============================================="
echo ""

# Configuration - EDIT THESE
REGION="${AWS_REGION:-us-east-1}"
INSTANCE_TYPE="g5.xlarge"           # A10G 24GB - $1.01/hr
AMI=""                               # Will auto-detect
KEY_NAME="${AWS_KEY_NAME:-}"         # Your SSH key pair name
SECURITY_GROUP="${AWS_SG:-}"         # Security group with SSH access

# Auto-detect the Deep Learning AMI
echo "[1/4] Finding Deep Learning AMI..."
AMI=$(aws ec2 describe-images \
    --region "$REGION" \
    --owners amazon \
    --filters \
        "Name=name,Values=Deep Learning AMI GPU PyTorch*Ubuntu*" \
        "Name=state,Values=available" \
    --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
    --output text 2>/dev/null || echo "")

if [ -z "$AMI" ] || [ "$AMI" = "None" ]; then
    # Fallback to standard Ubuntu AMI
    AMI=$(aws ec2 describe-images \
        --region "$REGION" \
        --owners 099720109477 \
        --filters \
            "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64*" \
            "Name=state,Values=available" \
        --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
        --output text)
    echo "  Using Ubuntu AMI: $AMI (will need driver setup)"
else
    echo "  Using Deep Learning AMI: $AMI"
fi

# Check for required config
if [ -z "$KEY_NAME" ]; then
    echo ""
    echo "[ERROR] AWS_KEY_NAME not set."
    echo "  Set it with: export AWS_KEY_NAME=your-key-pair-name"
    echo "  Or create one: aws ec2 create-key-pair --key-name mk-training --query KeyMaterial --output text > mk-training.pem"
    exit 1
fi

# Create security group if not specified
if [ -z "$SECURITY_GROUP" ]; then
    echo "[2/4] Creating security group..."
    SECURITY_GROUP=$(aws ec2 create-security-group \
        --region "$REGION" \
        --group-name "mk-training-sg" \
        --description "MK training instance - SSH access" \
        --query 'GroupId' \
        --output text 2>/dev/null || \
        aws ec2 describe-security-groups \
            --region "$REGION" \
            --group-names "mk-training-sg" \
            --query 'SecurityGroups[0].GroupId' \
            --output text)

    # Allow SSH
    aws ec2 authorize-security-group-ingress \
        --region "$REGION" \
        --group-id "$SECURITY_GROUP" \
        --protocol tcp \
        --port 22 \
        --cidr 0.0.0.0/0 2>/dev/null || true

    echo "  Security group: $SECURITY_GROUP"
else
    echo "[2/4] Using security group: $SECURITY_GROUP"
fi

# Launch instance
echo "[3/4] Launching $INSTANCE_TYPE instance..."
INSTANCE_ID=$(aws ec2 run-instances \
    --region "$REGION" \
    --image-id "$AMI" \
    --instance-type "$INSTANCE_TYPE" \
    --key-name "$KEY_NAME" \
    --security-group-ids "$SECURITY_GROUP" \
    --block-device-mappings "DeviceName=/dev/sda1,Ebs={VolumeSize=100,VolumeType=gp3}" \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=mk-training}]" \
    --query 'Instances[0].InstanceId' \
    --output text)

echo "  Instance ID: $INSTANCE_ID"
echo "  Waiting for instance to start..."

# Wait for instance
aws ec2 wait instance-running --region "$REGION" --instance-ids "$INSTANCE_ID"

# Get public IP
PUBLIC_IP=$(aws ec2 describe-instances \
    --region "$REGION" \
    --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)

echo ""
echo "[4/4] Instance is running!"
echo ""
echo "=============================================="
echo "  Instance Details"
echo "=============================================="
echo "  Instance ID:  $INSTANCE_ID"
echo "  Public IP:    $PUBLIC_IP"
echo "  Instance:     $INSTANCE_TYPE (A10G 24GB)"
echo "  Cost:         ~\$1.01/hour"
echo "  Region:       $REGION"
echo ""
echo "=============================================="
echo "  Next Steps"
echo "=============================================="
echo ""
echo "  1. SSH into the instance:"
echo "     ssh -i ~/.ssh/${KEY_NAME}.pem ubuntu@${PUBLIC_IP}"
echo ""
echo "  2. Clone MK repo and run setup:"
echo "     git clone https://github.com/mohd2456/MK.git"
echo "     cd MK/training"
echo "     mkdir -p ~/mk-training/{data,scripts}"
echo "     cp data/* ~/mk-training/data/"
echo "     cp scripts/* ~/mk-training/scripts/"
echo "     cd ~/mk-training"
echo "     chmod +x ../MK/training/aws/setup.sh"
echo "     ../MK/training/aws/setup.sh"
echo ""
echo "  3. Run training:"
echo "     chmod +x ../MK/training/aws/train.sh"
echo "     ../MK/training/aws/train.sh"
echo ""
echo "  4. IMPORTANT — When done, TERMINATE the instance:"
echo "     aws ec2 terminate-instances --region $REGION --instance-ids $INSTANCE_ID"
echo ""
echo "  Estimated total cost: \$3-10 (1-3 hours of training)"
echo ""

# Save instance info for later
echo "$INSTANCE_ID" > /tmp/mk-training-instance-id
echo "$PUBLIC_IP" > /tmp/mk-training-instance-ip
