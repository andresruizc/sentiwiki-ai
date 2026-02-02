#!/bin/bash
# Check if subnets are public (have internet access)
# This helps diagnose ECS task connectivity issues
#
# NOTE: Use this for troubleshooting. Once subnets are public, they stay public.
# You typically only need this if tasks can't reach ECR/CloudWatch/Secrets Manager.

set -e

# Disable AWS CLI pager
export AWS_PAGER=""

# Load configuration
if [ -f "../infrastructure-ids.txt" ]; then
  source ../infrastructure-ids.txt
else
  echo "⚠️  infrastructure-ids.txt not found. Using defaults..."
  AWS_REGION=${AWS_REGION:-"eu-north-1"}
fi

echo "🔍 Checking subnet configuration..."
echo "   Region: ${AWS_REGION:-eu-north-1}"
echo ""

# Get subnet IDs from infrastructure-ids.txt or use provided
SUBNET_IDS_INPUT=${1:-$SUBNET_IDS}

if [ -z "$SUBNET_IDS_INPUT" ]; then
  echo "❌ No subnet IDs provided"
  echo "   Usage: ./check-subnet-public.sh [subnet-id1,subnet-id2,...]"
  exit 1
fi

# Convert comma-separated to space-separated
SUBNET_IDS_LIST=$(echo $SUBNET_IDS_INPUT | tr ',' ' ')

echo "Checking subnets: $SUBNET_IDS_LIST"
echo ""

for SUBNET_ID in $SUBNET_IDS_LIST; do
  echo "📡 Subnet: $SUBNET_ID"
  
  # Check MapPublicIpOnLaunch
  MAP_PUBLIC_IP=$(aws ec2 describe-subnets \
    --subnet-ids $SUBNET_ID \
    --query "Subnets[0].MapPublicIpOnLaunch" \
    --output text \
    --region ${AWS_REGION:-eu-north-1} 2>/dev/null || echo "unknown")
  
  # Get route table
  RT_ID=$(aws ec2 describe-route-tables \
    --filters "Name=association.subnet-id,Values=$SUBNET_ID" \
    --query "RouteTables[0].RouteTableId" \
    --output text \
    --region ${AWS_REGION:-eu-north-1} 2>/dev/null || echo "none")
  
  # Check for Internet Gateway route
  IGW_ROUTE=$(aws ec2 describe-route-tables \
    --route-table-ids $RT_ID \
    --query "RouteTables[0].Routes[?GatewayId!='null' && GatewayId!='local']" \
    --output json \
    --region ${AWS_REGION:-eu-north-1} 2>/dev/null || echo "[]")
  
  HAS_IGW=$(echo $IGW_ROUTE | grep -q "igw-" && echo "yes" || echo "no")
  
  # Determine if public
  if [ "$MAP_PUBLIC_IP" = "true" ] && [ "$HAS_IGW" = "yes" ]; then
    echo "   ✅ PUBLIC - Has internet access"
  elif [ "$MAP_PUBLIC_IP" = "true" ] || [ "$HAS_IGW" = "yes" ]; then
    echo "   ⚠️  PARTIALLY PUBLIC - May have issues"
  else
    echo "   ❌ PRIVATE - No internet access"
    echo "      Tasks in this subnet cannot reach ECR or CloudWatch"
  fi
  
  echo "   - MapPublicIpOnLaunch: $MAP_PUBLIC_IP"
  echo "   - Route Table: $RT_ID"
  echo "   - Has IGW Route: $HAS_IGW"
  echo ""
done

echo "💡 For ECS Fargate with assignPublicIp=ENABLED:"
echo "   ✅ Use PUBLIC subnets (MapPublicIpOnLaunch=true + IGW route)"
echo "   ❌ PRIVATE subnets will fail to pull images or send logs"

