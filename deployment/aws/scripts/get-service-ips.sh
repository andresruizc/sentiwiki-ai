#!/bin/bash
# Get service URLs and status for ECS services
# Shows ALB URL for API/Frontend and IPs for other services

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

CLUSTER="esa-iagen-cluster"
REGION=$AWS_REGION

echo "🌐 ESA-IAGEN Service URLs"
echo "   Cluster: $CLUSTER"
echo "   Region: $REGION"
echo ""

# ============================================
# ALB URLs (API and Frontend)
# ============================================
echo "════════════════════════════════════════════"
echo "🔗 APPLICATION (via Load Balancer)"
echo "════════════════════════════════════════════"
echo ""

if [ -n "$ALB_DNS_NAME" ]; then
  echo "📡 Application Load Balancer:"
  echo "   ✅ DNS Name: $ALB_DNS_NAME"
  echo ""
  echo "   🖥️  Frontend:  http://$ALB_DNS_NAME/"
  echo "   🔌 API:       http://$ALB_DNS_NAME/api/"
  echo "   ❤️  Health:    http://$ALB_DNS_NAME/api/health"
  echo ""
else
  echo "⚠️  ALB_DNS_NAME not found in infrastructure-ids.txt"
  echo "   Run setup-infrastructure.sh first."
  echo ""
fi

# Function to check if service is running
check_service_status() {
  SERVICE_NAME=$1
  STATUS=$(aws ecs describe-services \
    --cluster $CLUSTER \
    --services $SERVICE_NAME \
    --region $REGION \
    --query 'services[0].runningCount' \
    --output text 2>/dev/null || echo "0")

  if [ "$STATUS" != "0" ] && [ "$STATUS" != "None" ] && [ -n "$STATUS" ]; then
    echo "✅"
  else
    echo "❌"
  fi
}

# Check API and Frontend status
API_STATUS=$(check_service_status "esa-iagen-api-service")
FRONTEND_STATUS=$(check_service_status "esa-iagen-frontend-service")

echo "   Service Status:"
echo "   - API Service:      $API_STATUS"
echo "   - Frontend Service: $FRONTEND_STATUS"
echo ""

# ============================================
# Internal Services (Qdrant - direct access)
# ============================================
echo "════════════════════════════════════════════"
echo "🗄️  INTERNAL SERVICES (direct IP access)"
echo "════════════════════════════════════════════"
echo ""

# Function to get IP for a service
get_service_ip() {
  SERVICE_NAME=$1
  PORT=$2
  DISPLAY_NAME=$3
  echo "📡 $DISPLAY_NAME:"

  # Get task ARN
  TASK_ARN=$(aws ecs list-tasks \
    --cluster $CLUSTER \
    --service-name $SERVICE_NAME \
    --region $REGION \
    --query 'taskArns[0]' \
    --output text 2>/dev/null || echo "")

  if [ -z "$TASK_ARN" ] || [ "$TASK_ARN" = "None" ] || [ "$TASK_ARN" = "null" ]; then
    echo "   ⚠️  No running tasks found"
    echo ""
    return
  fi

  # Get network interface ID
  ENI_ID=$(aws ecs describe-tasks \
    --cluster $CLUSTER \
    --tasks $TASK_ARN \
    --region $REGION \
    --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' \
    --output text 2>/dev/null || echo "")

  if [ -z "$ENI_ID" ] || [ "$ENI_ID" = "None" ] || [ "$ENI_ID" = "null" ]; then
    echo "   ⚠️  No network interface found"
    echo ""
    return
  fi

  # Get public IP
  PUBLIC_IP=$(aws ec2 describe-network-interfaces \
    --network-interface-ids $ENI_ID \
    --region $REGION \
    --query 'NetworkInterfaces[0].Association.PublicIp' \
    --output text 2>/dev/null || echo "")

  if [ -n "$PUBLIC_IP" ] && [ "$PUBLIC_IP" != "None" ] && [ "$PUBLIC_IP" != "null" ]; then
    echo "   ✅ Public IP: $PUBLIC_IP"
    if [ -n "$PORT" ]; then
      echo "   🔗 URL: http://$PUBLIC_IP:$PORT"
    fi
  else
    echo "   ⚠️  No public IP (internal only via Service Discovery)"
    echo "   📍 Internal: $SERVICE_NAME.esa-iagen.local:$PORT"
  fi
  echo ""
}

# Get Qdrant IP (not behind ALB)
get_service_ip "esa-iagen-qdrant-service" "6333" "Qdrant Vector DB"

# ============================================
# Monitoring Services (optional)
# ============================================
PROMETHEUS_EXISTS=$(aws ecs describe-services --cluster $CLUSTER --services esa-iagen-prometheus-service --region $REGION --query 'services[0].status' --output text 2>/dev/null || echo "")
GRAFANA_EXISTS=$(aws ecs describe-services --cluster $CLUSTER --services esa-iagen-grafana-service --region $REGION --query 'services[0].status' --output text 2>/dev/null || echo "")

if [ "$PROMETHEUS_EXISTS" = "ACTIVE" ] || [ "$GRAFANA_EXISTS" = "ACTIVE" ]; then
  echo "════════════════════════════════════════════"
  echo "📊 MONITORING SERVICES"
  echo "════════════════════════════════════════════"
  echo ""
  if [ "$PROMETHEUS_EXISTS" = "ACTIVE" ]; then
    get_service_ip "esa-iagen-prometheus-service" "9090" "Prometheus"
  fi
  if [ "$GRAFANA_EXISTS" = "ACTIVE" ]; then
    get_service_ip "esa-iagen-grafana-service" "3002" "Grafana"
  fi
fi

# ============================================
# Summary
# ============================================
echo "════════════════════════════════════════════"
echo "📋 QUICK ACCESS"
echo "════════════════════════════════════════════"
echo ""
if [ -n "$ALB_DNS_NAME" ]; then
  echo "🚀 Open your app:  http://$ALB_DNS_NAME/"
  echo "🔧 API health:     http://$ALB_DNS_NAME/api/health"
fi
echo ""
