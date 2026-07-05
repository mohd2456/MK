#!/usr/bin/env bash
#
# MK Training — Terminate AWS Instance
#
# ALWAYS run this when training is complete to stop billing!
#
# Usage:
#   ./terminate-instance.sh
#   ./terminate-instance.sh <instance-id>
#

set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"

# Get instance ID
if [ -n "${1:-}" ]; then
    INSTANCE_ID="$1"
elif [ -f /tmp/mk-training-instance-id ]; then
    INSTANCE_ID=$(cat /tmp/mk-training-instance-id)
else
    echo "Usage: ./terminate-instance.sh <instance-id>"
    echo ""
    echo "Find your instance:"
    echo "  aws ec2 describe-instances --region $REGION --filters 'Name=tag:Name,Values=mk-training' --query 'Reservations[].Instances[].InstanceId' --output text"
    exit 1
fi

echo "Terminating instance: $INSTANCE_ID"
aws ec2 terminate-instances --region "$REGION" --instance-ids "$INSTANCE_ID"

echo ""
echo "Instance $INSTANCE_ID is being terminated."
echo "Billing will stop shortly."
echo ""
echo "Verify with:"
echo "  aws ec2 describe-instances --region $REGION --instance-ids $INSTANCE_ID --query 'Reservations[].Instances[].State.Name' --output text"
