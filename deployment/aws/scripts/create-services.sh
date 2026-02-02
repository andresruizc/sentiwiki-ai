#!/bin/bash
# Create ECS Services
# This script creates all ECS services

set -e

# Disable AWS CLI pager to prevent hanging
export AWS_PAGER=""

# Load infrastructure IDs
if [ ! -f "../infrastructure-ids.txt" ]; then
  echo "❌ infrastructure-ids.txt not found. Run setup-infrastructure.sh first."
  exit 1
fi

source ../infrastructure-ids.txt

echo "🚀 Creating ECS services..."
echo "   Region: $AWS_REGION"
echo "   Cluster: esa-iagen-cluster"
echo ""

# Convert subnet IDs to array format for AWS CLI
# Handle both space-separated and comma-separated (from infrastructure-ids.txt)
# First convert any spaces to commas, then use as-is
SUBNET_ARRAY=$(echo $SUBNET_IDS | tr ' ' ',')

# 1. Create Service Discovery services
echo "🔍 Creating service discovery services..."

# Qdrant service discovery
QDRANT_SERVICE_ID=$(aws servicediscovery create-service \
  --name qdrant \
  --namespace-id $NAMESPACE_ID \
  --dns-config "NamespaceId=$NAMESPACE_ID,DnsRecords=[{Type=A,TTL=60}]" \
  --health-check-custom-config "FailureThreshold=1" \
  --region $AWS_REGION \
  --query 'Service.Id' \
  --output text 2>/dev/null || \
  aws servicediscovery list-services \
    --filters "Name=NAMESPACE_ID,Values=$NAMESPACE_ID" \
    --query "Services[?Name=='qdrant'].Id" \
    --output text \
    --region $AWS_REGION | head -1)

echo "✅ Qdrant service discovery: $QDRANT_SERVICE_ID"

# API service discovery
API_SERVICE_ID=$(aws servicediscovery create-service \
  --name api \
  --namespace-id $NAMESPACE_ID \
  --dns-config "NamespaceId=$NAMESPACE_ID,DnsRecords=[{Type=A,TTL=60}]" \
  --health-check-custom-config "FailureThreshold=1" \
  --region $AWS_REGION \
  --query 'Service.Id' \
  --output text 2>/dev/null || \
  aws servicediscovery list-services \
    --filters "Name=NAMESPACE_ID,Values=$NAMESPACE_ID" \
    --query "Services[?Name=='api'].Id" \
    --output text \
    --region $AWS_REGION | head -1)

echo "✅ API service discovery: $API_SERVICE_ID"

# Frontend service discovery
FRONTEND_SERVICE_ID=$(aws servicediscovery create-service \
  --name frontend \
  --namespace-id $NAMESPACE_ID \
  --dns-config "NamespaceId=$NAMESPACE_ID,DnsRecords=[{Type=A,TTL=60}]" \
  --health-check-custom-config "FailureThreshold=1" \
  --region $AWS_REGION \
  --query 'Service.Id' \
  --output text 2>/dev/null || \
  aws servicediscovery list-services \
    --filters "Name=NAMESPACE_ID,Values=$NAMESPACE_ID" \
    --query "Services[?Name=='frontend'].Id" \
    --output text \
    --region $AWS_REGION | head -1)

echo "✅ Frontend service discovery: $FRONTEND_SERVICE_ID"

# Optional: Prometheus and Grafana service discovery (monitoring - not required)
# Uncomment below if you want to add monitoring later
# PROMETHEUS_SERVICE_ID=$(aws servicediscovery create-service \
#   --name prometheus \
#   --namespace-id $NAMESPACE_ID \
#   --dns-config "NamespaceId=$NAMESPACE_ID,DnsRecords=[{Type=A,TTL=60}]" \
#   --health-check-custom-config "FailureThreshold=1" \
#   --region $AWS_REGION \
#   --query 'Service.Id' \
#   --output text 2>/dev/null || \
#   aws servicediscovery list-services \
#     --filters "Name=NAMESPACE_ID,Values=$NAMESPACE_ID" \
#     --query "Services[?Name=='prometheus'].Id" \
#     --output text \
#     --region $AWS_REGION | head -1)
# echo "✅ Prometheus service discovery: $PROMETHEUS_SERVICE_ID"
#
# GRAFANA_SERVICE_ID=$(aws servicediscovery create-service \
#   --name grafana \
#   --namespace-id $NAMESPACE_ID \
#   --dns-config "NamespaceId=$NAMESPACE_ID,DnsRecords=[{Type=A,TTL=60}]" \
#   --health-check-custom-config "FailureThreshold=1" \
#   --region $AWS_REGION \
#   --query 'Service.Id' \
#   --output text 2>/dev/null || \
#   aws servicediscovery list-services \
#     --filters "Name=NAMESPACE_ID,Values=$NAMESPACE_ID" \
#     --query "Services[?Name=='grafana'].Id" \
#     --output text \
#     --region $AWS_REGION | head -1)
# echo "✅ Grafana service discovery: $GRAFANA_SERVICE_ID"

# 2. Create ECS Services
echo ""
echo "📦 Creating ECS services..."

# Qdrant service
echo "Creating Qdrant service..."
aws ecs create-service \
  --cluster esa-iagen-cluster \
  --service-name esa-iagen-qdrant-service \
  --task-definition esa-iagen-qdrant \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_ARRAY],securityGroups=[$SECURITY_GROUP_ID],assignPublicIp=ENABLED}" \
  --service-registries "registryArn=arn:aws:servicediscovery:$AWS_REGION:$AWS_ACCOUNT_ID:service/$QDRANT_SERVICE_ID" \
  --region $AWS_REGION \
  --query 'service.serviceName' \
  --output text 2>/dev/null || echo "Qdrant service may already exist"
echo "✅ Qdrant service created"

# API service (depends on Qdrant)
echo "Creating API service..."

# Check if task definition exists first
TASK_DEF_EXISTS=$(aws ecs describe-task-definition \
  --task-definition esa-iagen-api \
  --region $AWS_REGION \
  --query 'taskDefinition.taskDefinitionArn' \
  --output text 2>/dev/null || echo "NOT_FOUND")

if [ "$TASK_DEF_EXISTS" = "NOT_FOUND" ]; then
  echo "❌ Error: Task definition 'esa-iagen-api' does not exist!"
  echo "   Please run: cd aws/scripts && ./register-task-definitions.sh"
  exit 1
fi

# Check if service already exists and its status
SERVICE_STATUS=$(aws ecs describe-services \
  --cluster esa-iagen-cluster \
  --services esa-iagen-api-service \
  --region $AWS_REGION \
  --query 'services[0].status' \
  --output text 2>/dev/null || echo "NOT_FOUND")

if [ "$SERVICE_STATUS" = "NOT_FOUND" ] || [ -z "$SERVICE_STATUS" ] || [ "$SERVICE_STATUS" = "None" ]; then
  # Service doesn't exist - create it
  # Check if ALB target group exists (from infrastructure-ids.txt)
  if [ -n "$TARGET_GROUP_ARN" ] && [ "$TARGET_GROUP_ARN" != "None" ]; then
    echo "  Registering API service with ALB target group..."
    CREATE_OUTPUT=$(aws ecs create-service \
      --cluster esa-iagen-cluster \
      --service-name esa-iagen-api-service \
      --task-definition esa-iagen-api \
      --desired-count 1 \
      --launch-type FARGATE \
      --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_ARRAY],securityGroups=[$SECURITY_GROUP_ID],assignPublicIp=ENABLED}" \
      --service-registries "registryArn=arn:aws:servicediscovery:$AWS_REGION:$AWS_ACCOUNT_ID:service/$API_SERVICE_ID" \
      --load-balancers "targetGroupArn=$TARGET_GROUP_ARN,containerName=api,containerPort=8000" \
      --region $AWS_REGION \
      --query 'service.serviceName' \
      --output text 2>&1)
  else
    # Fallback: create without ALB (for backward compatibility)
    echo "  ⚠️  ALB target group not found, creating service without load balancer..."
    CREATE_OUTPUT=$(aws ecs create-service \
  --cluster esa-iagen-cluster \
  --service-name esa-iagen-api-service \
  --task-definition esa-iagen-api \
  --desired-count 1 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_ARRAY],securityGroups=[$SECURITY_GROUP_ID],assignPublicIp=ENABLED}" \
  --service-registries "registryArn=arn:aws:servicediscovery:$AWS_REGION:$AWS_ACCOUNT_ID:service/$API_SERVICE_ID" \
  --region $AWS_REGION \
  --query 'service.serviceName' \
      --output text 2>&1)
  fi
  
  if [ $? -eq 0 ]; then
    echo "✅ API service created: $CREATE_OUTPUT"
  else
    echo "❌ Failed to create API service:"
    echo "$CREATE_OUTPUT"
    if echo "$CREATE_OUTPUT" | grep -q "DRAINING"; then
      echo ""
      echo "💡 Service is in DRAINING state. Run: ./fix-draining-service.sh esa-iagen-api-service"
    fi
    exit 1
  fi
elif [ "$SERVICE_STATUS" = "DRAINING" ]; then
  echo "⚠️  API service exists but is in DRAINING state (being deleted)"
  echo "   Run: ./fix-draining-service.sh esa-iagen-api-service"
  echo "   Then run this script again"
  exit 1
elif [ "$SERVICE_STATUS" = "ACTIVE" ]; then
  echo "✅ API service already exists and is ACTIVE"
else
  echo "⚠️  API service exists with status: $SERVICE_STATUS"
fi

# Frontend service (depends on API) - with ALB integration
echo "Creating Frontend service..."

# Check if frontend service already exists
FRONTEND_SERVICE_STATUS=$(aws ecs describe-services \
  --cluster esa-iagen-cluster \
  --services esa-iagen-frontend-service \
  --region $AWS_REGION \
  --query 'services[0].status' \
  --output text 2>/dev/null || echo "NOT_FOUND")

if [ "$FRONTEND_SERVICE_STATUS" = "NOT_FOUND" ] || [ -z "$FRONTEND_SERVICE_STATUS" ] || [ "$FRONTEND_SERVICE_STATUS" = "None" ]; then
  # Check if frontend target group exists (from infrastructure-ids.txt)
  if [ -n "$FRONTEND_TARGET_GROUP_ARN" ] && [ "$FRONTEND_TARGET_GROUP_ARN" != "None" ]; then
    echo "  Registering Frontend service with ALB target group..."
    aws ecs create-service \
      --cluster esa-iagen-cluster \
      --service-name esa-iagen-frontend-service \
      --task-definition esa-iagen-frontend \
      --desired-count 1 \
      --launch-type FARGATE \
      --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_ARRAY],securityGroups=[$SECURITY_GROUP_ID],assignPublicIp=ENABLED}" \
      --service-registries "registryArn=arn:aws:servicediscovery:$AWS_REGION:$AWS_ACCOUNT_ID:service/$FRONTEND_SERVICE_ID" \
      --load-balancers "targetGroupArn=$FRONTEND_TARGET_GROUP_ARN,containerName=frontend,containerPort=3000" \
      --region $AWS_REGION \
      --query 'service.serviceName' \
      --output text 2>/dev/null || echo "Frontend service may already exist"
  else
    # Fallback: create without ALB (for backward compatibility)
    echo "  ⚠️  Frontend target group not found, creating service without load balancer..."
    aws ecs create-service \
      --cluster esa-iagen-cluster \
      --service-name esa-iagen-frontend-service \
      --task-definition esa-iagen-frontend \
      --desired-count 1 \
      --launch-type FARGATE \
      --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_ARRAY],securityGroups=[$SECURITY_GROUP_ID],assignPublicIp=ENABLED}" \
      --service-registries "registryArn=arn:aws:servicediscovery:$AWS_REGION:$AWS_ACCOUNT_ID:service/$FRONTEND_SERVICE_ID" \
      --region $AWS_REGION \
      --query 'service.serviceName' \
      --output text 2>/dev/null || echo "Frontend service may already exist"
  fi
  echo "✅ Frontend service created"
elif [ "$FRONTEND_SERVICE_STATUS" = "ACTIVE" ]; then
  echo "✅ Frontend service already exists and is ACTIVE"
else
  echo "⚠️  Frontend service exists with status: $FRONTEND_SERVICE_STATUS"
fi

# Monitoring: Prometheus and Grafana services (optional but recommended)
# Set SKIP_MONITORING=true to skip monitoring deployment
if [ "${SKIP_MONITORING:-false}" != "true" ]; then
  echo ""
  echo "📊 Creating monitoring services..."
  
  # Create service discovery for Prometheus
  echo "  Creating Prometheus service discovery..."
  PROMETHEUS_SERVICE_ID=$(aws servicediscovery create-service \
    --name prometheus \
    --namespace-id $NAMESPACE_ID \
    --dns-config "NamespaceId=$NAMESPACE_ID,RoutingPolicy=MULTIVALUE,DnsRecords=[{Type=A,TTL=60}]" \
    --region $AWS_REGION \
    --query 'Service.Id' \
    --output text 2>/dev/null || echo "")
  
  if [ -z "$PROMETHEUS_SERVICE_ID" ] || [ "$PROMETHEUS_SERVICE_ID" = "None" ]; then
    PROMETHEUS_SERVICE_ID=$(aws servicediscovery list-services \
      --filters "Name=NAMESPACE_ID,Values=$NAMESPACE_ID" \
      --region $AWS_REGION \
      --query "Services[?Name=='prometheus'].Id" \
      --output text 2>/dev/null || echo "")
  fi
  echo "  ✅ Prometheus service discovery: $PROMETHEUS_SERVICE_ID"
  
  # Create service discovery for Grafana
  echo "  Creating Grafana service discovery..."
  GRAFANA_SERVICE_ID=$(aws servicediscovery create-service \
    --name grafana \
    --namespace-id $NAMESPACE_ID \
    --dns-config "NamespaceId=$NAMESPACE_ID,RoutingPolicy=MULTIVALUE,DnsRecords=[{Type=A,TTL=60}]" \
    --region $AWS_REGION \
    --query 'Service.Id' \
    --output text 2>/dev/null || echo "")
  
  if [ -z "$GRAFANA_SERVICE_ID" ] || [ "$GRAFANA_SERVICE_ID" = "None" ]; then
    GRAFANA_SERVICE_ID=$(aws servicediscovery list-services \
      --filters "Name=NAMESPACE_ID,Values=$NAMESPACE_ID" \
      --region $AWS_REGION \
      --query "Services[?Name=='grafana'].Id" \
      --output text 2>/dev/null || echo "")
  fi
  echo "  ✅ Grafana service discovery: $GRAFANA_SERVICE_ID"
  
  # Add security group rules for monitoring
  echo "  Adding security group rules for monitoring..."
  aws ec2 authorize-security-group-ingress \
    --group-id $SECURITY_GROUP_ID \
    --protocol tcp \
    --port 9090 \
    --cidr 0.0.0.0/0 \
    --region $AWS_REGION \
    --no-cli-pager \
    >/dev/null 2>&1 || echo "    Port 9090 rule already exists"
  aws ec2 authorize-security-group-ingress \
    --group-id $SECURITY_GROUP_ID \
    --protocol tcp \
    --port 3002 \
    --cidr 0.0.0.0/0 \
    --region $AWS_REGION \
    --no-cli-pager \
    >/dev/null 2>&1 || echo "    Port 3002 rule already exists"
  
  # Create Prometheus service
  echo "  Creating Prometheus service..."
  aws ecs create-service \
    --cluster esa-iagen-cluster \
    --service-name esa-iagen-prometheus-service \
    --task-definition esa-iagen-prometheus \
    --desired-count 1 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_ARRAY],securityGroups=[$SECURITY_GROUP_ID],assignPublicIp=ENABLED}" \
    --service-registries "registryArn=arn:aws:servicediscovery:$AWS_REGION:$AWS_ACCOUNT_ID:service/$PROMETHEUS_SERVICE_ID" \
    --region $AWS_REGION \
    --query 'service.serviceName' \
    --output text 2>/dev/null || echo "Prometheus service may already exist"
  echo "  ✅ Prometheus service created"
  
  # Create Grafana service
  echo "  Creating Grafana service..."
  aws ecs create-service \
    --cluster esa-iagen-cluster \
    --service-name esa-iagen-grafana-service \
    --task-definition esa-iagen-grafana \
    --desired-count 1 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_ARRAY],securityGroups=[$SECURITY_GROUP_ID],assignPublicIp=ENABLED}" \
    --service-registries "registryArn=arn:aws:servicediscovery:$AWS_REGION:$AWS_ACCOUNT_ID:service/$GRAFANA_SERVICE_ID" \
    --region $AWS_REGION \
    --query 'service.serviceName' \
    --output text 2>/dev/null || echo "Grafana service may already exist"
  echo "  ✅ Grafana service created"
else
  echo ""
  echo "⏭️  Skipping monitoring (SKIP_MONITORING=true)"
fi

echo ""
echo "✅ ECS services created successfully!"
echo "   - Qdrant, API, Frontend (essential)"
if [ "${SKIP_MONITORING:-false}" != "true" ]; then
  echo "   - Prometheus, Grafana (monitoring)"
fi
echo ""
echo "💡 Tip: To skip monitoring, run: SKIP_MONITORING=true ./create-services.sh"
echo ""
echo "Next steps:"
echo "1. Set up AWS Secrets Manager for API keys (or use environment variables - see documentation)"
echo "2. Run ./sync-api-cors.sh after services start"
echo "3. Run ./get-service-ips.sh to get service URLs"
if [ "${SKIP_MONITORING:-false}" != "true" ]; then
  echo "4. Configure Grafana: Add Prometheus data source (http://prometheus.esa-iagen.local:9090)"
fi
echo ""
echo "Check service status: aws ecs list-services --cluster esa-iagen-cluster --region $AWS_REGION"

