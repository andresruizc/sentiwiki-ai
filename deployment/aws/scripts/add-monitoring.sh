#!/bin/bash
#
# Add Prometheus + Grafana monitoring to existing ECS deployment
# Run this AFTER the main infrastructure is deployed
#

set -e

echo "🔍 Adding Monitoring (Prometheus + Grafana) to ESA-IAGEN..."
echo ""

# Load infrastructure IDs
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -f "../infrastructure-ids.txt" ]; then
    echo "❌ Error: infrastructure-ids.txt not found"
    echo "   Run setup-infrastructure.sh first"
    exit 1
fi

source ../infrastructure-ids.txt

echo "📋 Using infrastructure:"
echo "   Region: $AWS_REGION"
echo "   Account: $AWS_ACCOUNT_ID"
echo "   VPC: $VPC_ID"
echo "   Security Group: $SECURITY_GROUP_ID"
echo "   Namespace: $NAMESPACE_ID"
echo ""

# Function to replace placeholders in task definitions
replace_placeholders() {
    local file=$1
    sed -i.bak \
        -e "s/YOUR_ACCOUNT_ID/$AWS_ACCOUNT_ID/g" \
        -e "s/YOUR_REGION/$AWS_REGION/g" \
        "$file"
    rm -f "${file}.bak"
}

# Step 1: Add Security Group Rules
echo "🔒 Step 1: Adding security group rules..."

# Prometheus (9090)
aws ec2 authorize-security-group-ingress \
    --group-id $SECURITY_GROUP_ID \
    --protocol tcp \
    --port 9090 \
    --cidr 0.0.0.0/0 \
    --region $AWS_REGION 2>/dev/null || echo "   Port 9090 rule already exists"

# Grafana (3002) - different from frontend (3000)
aws ec2 authorize-security-group-ingress \
    --group-id $SECURITY_GROUP_ID \
    --protocol tcp \
    --port 3002 \
    --cidr 0.0.0.0/0 \
    --region $AWS_REGION 2>/dev/null || echo "   Port 3002 rule already exists"

echo "✅ Security group rules added"

# Step 2: Register Task Definitions
echo ""
echo "📦 Step 2: Registering task definitions..."

# Prometheus
echo "   Registering Prometheus..."
replace_placeholders "../task-definitions/task-prometheus.json"
aws ecs register-task-definition \
    --cli-input-json file://../task-definitions/task-prometheus.json \
    --region $AWS_REGION \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text
echo "   ✅ Prometheus task definition registered"

# Grafana
echo "   Registering Grafana..."
replace_placeholders "../task-definitions/task-grafana.json"
aws ecs register-task-definition \
    --cli-input-json file://../task-definitions/task-grafana.json \
    --region $AWS_REGION \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text
echo "   ✅ Grafana task definition registered"

# Step 3: Create Service Discovery entries
echo ""
echo "🔗 Step 3: Creating service discovery entries..."

PROMETHEUS_SERVICE_ID=$(aws servicediscovery create-service \
    --name prometheus \
    --namespace-id $NAMESPACE_ID \
    --dns-config "NamespaceId=$NAMESPACE_ID,DnsRecords=[{Type=A,TTL=60}]" \
    --health-check-custom-config "FailureThreshold=1" \
    --region $AWS_REGION \
    --query 'Service.Id' \
    --output text 2>/dev/null || \
    aws servicediscovery list-services \
        --filters "Name=NAMESPACE_ID,Values=$NAMESPACE_ID" \
        --query "Services[?Name=='prometheus'].Id" \
        --output text \
        --region $AWS_REGION | head -1)
echo "   ✅ Prometheus service discovery: $PROMETHEUS_SERVICE_ID"

GRAFANA_SERVICE_ID=$(aws servicediscovery create-service \
    --name grafana \
    --namespace-id $NAMESPACE_ID \
    --dns-config "NamespaceId=$NAMESPACE_ID,DnsRecords=[{Type=A,TTL=60}]" \
    --health-check-custom-config "FailureThreshold=1" \
    --region $AWS_REGION \
    --query 'Service.Id' \
    --output text 2>/dev/null || \
    aws servicediscovery list-services \
        --filters "Name=NAMESPACE_ID,Values=$NAMESPACE_ID" \
        --query "Services[?Name=='grafana'].Id" \
        --output text \
        --region $AWS_REGION | head -1)
echo "   ✅ Grafana service discovery: $GRAFANA_SERVICE_ID"

# Step 4: Create ECS Services
echo ""
echo "🚀 Step 4: Creating ECS services..."

# Get subnet IDs
SUBNET_IDS=$(aws ec2 describe-subnets \
    --filters "Name=vpc-id,Values=$VPC_ID" \
    --query 'Subnets[*].SubnetId' \
    --output text \
    --region $AWS_REGION | tr '\t' ',')

# Prometheus service
echo "   Creating Prometheus service..."
aws ecs create-service \
    --cluster esa-iagen-cluster \
    --service-name esa-iagen-prometheus-service \
    --task-definition esa-iagen-prometheus \
    --desired-count 1 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[${SUBNET_IDS%,}],securityGroups=[$SECURITY_GROUP_ID],assignPublicIp=ENABLED}" \
    --service-registries "registryArn=arn:aws:servicediscovery:$AWS_REGION:$AWS_ACCOUNT_ID:service/$PROMETHEUS_SERVICE_ID" \
    --region $AWS_REGION \
    --query 'service.serviceName' \
    --output text 2>/dev/null || echo "   Prometheus service may already exist"
echo "   ✅ Prometheus service created"

# Grafana service
echo "   Creating Grafana service..."
aws ecs create-service \
    --cluster esa-iagen-cluster \
    --service-name esa-iagen-grafana-service \
    --task-definition esa-iagen-grafana \
    --desired-count 1 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[${SUBNET_IDS%,}],securityGroups=[$SECURITY_GROUP_ID],assignPublicIp=ENABLED}" \
    --service-registries "registryArn=arn:aws:servicediscovery:$AWS_REGION:$AWS_ACCOUNT_ID:service/$GRAFANA_SERVICE_ID" \
    --region $AWS_REGION \
    --query 'service.serviceName' \
    --output text 2>/dev/null || echo "   Grafana service may already exist"
echo "   ✅ Grafana service created"

# Step 5: Wait for services to be running
echo ""
echo "⏳ Step 5: Waiting for services to start (this may take 2-3 minutes)..."

sleep 30

# Get IPs
echo ""
echo "🔍 Getting service IPs..."

# Prometheus IP
PROMETHEUS_TASK=$(aws ecs list-tasks \
    --cluster esa-iagen-cluster \
    --service-name esa-iagen-prometheus-service \
    --region $AWS_REGION \
    --query 'taskArns[0]' \
    --output text 2>/dev/null)

if [ "$PROMETHEUS_TASK" != "None" ] && [ -n "$PROMETHEUS_TASK" ]; then
    PROMETHEUS_ENI=$(aws ecs describe-tasks \
        --cluster esa-iagen-cluster \
        --tasks $PROMETHEUS_TASK \
        --region $AWS_REGION \
        --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' \
        --output text 2>/dev/null)
    
    PROMETHEUS_IP=$(aws ec2 describe-network-interfaces \
        --network-interface-ids $PROMETHEUS_ENI \
        --region $AWS_REGION \
        --query 'NetworkInterfaces[0].Association.PublicIp' \
        --output text 2>/dev/null)
fi

# Grafana IP
GRAFANA_TASK=$(aws ecs list-tasks \
    --cluster esa-iagen-cluster \
    --service-name esa-iagen-grafana-service \
    --region $AWS_REGION \
    --query 'taskArns[0]' \
    --output text 2>/dev/null)

if [ "$GRAFANA_TASK" != "None" ] && [ -n "$GRAFANA_TASK" ]; then
    GRAFANA_ENI=$(aws ecs describe-tasks \
        --cluster esa-iagen-cluster \
        --tasks $GRAFANA_TASK \
        --region $AWS_REGION \
        --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' \
        --output text 2>/dev/null)
    
    GRAFANA_IP=$(aws ec2 describe-network-interfaces \
        --network-interface-ids $GRAFANA_ENI \
        --region $AWS_REGION \
        --query 'NetworkInterfaces[0].Association.PublicIp' \
        --output text 2>/dev/null)
fi

echo ""
echo "=============================================="
echo "✅ MONITORING DEPLOYMENT COMPLETE!"
echo "=============================================="
echo ""
echo "📊 Access URLs:"
echo "   Prometheus: http://${PROMETHEUS_IP:-<pending>}:9090"
echo "   Grafana:    http://${GRAFANA_IP:-<pending>}:3002"
echo ""
echo "🔐 Grafana credentials:"
echo "   Username: admin"
echo "   Password: admin"
echo ""
echo "📝 Next steps:"
echo "   1. Open Grafana and add Prometheus as data source"
echo "   2. URL: http://prometheus.esa-iagen.local:9090"
echo "   3. Import RAG dashboard (see aws/grafana/dashboards/)"
echo ""
echo "💰 Additional cost: ~\$6/month"
echo ""

# Save monitoring IPs
cat >> ../infrastructure-ids.txt << EOF

# Monitoring (added by add-monitoring.sh)
PROMETHEUS_IP=$PROMETHEUS_IP
GRAFANA_IP=$GRAFANA_IP
EOF

echo "✅ IPs saved to infrastructure-ids.txt"

