#!/bin/bash
# Fix security groups by removing overly permissive rules
# This script removes 0.0.0.0/0 access to internal ports (8000, 3000, 6333)
# while keeping ALB port 80 open for external access

set -e
export AWS_PAGER=""

# Load configuration
if [ ! -f "../infrastructure-ids.txt" ]; then
  echo "❌ infrastructure-ids.txt not found. Run setup-infrastructure.sh first."
  exit 1
fi

source ../infrastructure-ids.txt

echo "🔒 Hardening security group rules..."
echo "   Security Group: $SECURITY_GROUP_ID"
echo "   Region: $AWS_REGION"
echo ""

# Function to revoke a rule (ignore errors if rule doesn't exist)
revoke_rule() {
  local port=$1
  local description=$2

  echo "   Removing 0.0.0.0/0 access to port $port ($description)..."
  aws ec2 revoke-security-group-ingress \
    --group-id "$SECURITY_GROUP_ID" \
    --protocol tcp \
    --port "$port" \
    --cidr 0.0.0.0/0 \
    --region "$AWS_REGION" \
    2>/dev/null && echo "   ✅ Removed" || echo "   ℹ️  Rule not found (already secure)"
}

echo "📋 Removing public access to internal ports..."
echo ""

# Remove public access to internal ports
revoke_rule 8000 "API"
revoke_rule 3000 "Frontend"
revoke_rule 6333 "Qdrant"
revoke_rule 9090 "Prometheus"
revoke_rule 3002 "Grafana"

echo ""
echo "✅ Security group hardening complete!"
echo ""
echo "📋 Current access model:"
echo "   ✅ Port 80 (ALB) - Open to internet for external access"
echo "   🔒 Port 8000 (API) - Internal only (via ALB + security group)"
echo "   🔒 Port 3000 (Frontend) - Internal only (via ALB + security group)"
echo "   🔒 Port 6333 (Qdrant) - Internal only (API can reach it)"
echo "   🔒 Port 9090 (Prometheus) - Internal only"
echo "   🔒 Port 3002 (Grafana) - Internal only"
echo ""
echo "💡 Services are still accessible via ALB DNS: $ALB_DNS_NAME"
echo ""
