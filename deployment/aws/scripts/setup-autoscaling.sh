#!/bin/bash
# Setup Auto Scaling for ECS Services
# Configures auto-scaling based on CPU and memory

set -e
export AWS_PAGER=""

# Load configuration
if [ ! -f "../infrastructure-ids.txt" ]; then
  echo "❌ infrastructure-ids.txt not found. Run setup-infrastructure.sh first."
  exit 1
fi

source ../infrastructure-ids.txt

CLUSTER_NAME="esa-iagen-cluster"
API_SERVICE="esa-iagen-api-service"

echo "⚖️  Setting up auto-scaling for ECS services..."
echo "   Region: $AWS_REGION"
echo "   Cluster: $CLUSTER_NAME"
echo ""

# Register scalable target for API service
echo "📈 Registering scalable target for API service..."
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --scalable-dimension ecs:service:DesiredCount \
  --resource-id "service/${CLUSTER_NAME}/${API_SERVICE}" \
  --min-capacity 1 \
  --max-capacity 5 \
  --region "$AWS_REGION" \
  2>/dev/null || echo "   Scalable target may already exist"

# Create CPU-based scaling policy
echo "   Creating CPU-based scaling policy..."
aws application-autoscaling put-scaling-policy \
  --service-namespace ecs \
  --scalable-dimension ecs:service:DesiredCount \
  --resource-id "service/${CLUSTER_NAME}/${API_SERVICE}" \
  --policy-name "api-cpu-scaling" \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration '{
    "TargetValue": 70.0,
    "PredefinedMetricSpecification": {
      "PredefinedMetricType": "ECSServiceAverageCPUUtilization"
    },
    "ScaleInCooldown": 300,
    "ScaleOutCooldown": 60
  }' \
  --region "$AWS_REGION" \
  2>/dev/null || echo "   Policy may already exist"

# Create memory-based scaling policy
echo "   Creating memory-based scaling policy..."
aws application-autoscaling put-scaling-policy \
  --service-namespace ecs \
  --scalable-dimension ecs:service:DesiredCount \
  --resource-id "service/${CLUSTER_NAME}/${API_SERVICE}" \
  --policy-name "api-memory-scaling" \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration '{
    "TargetValue": 80.0,
    "PredefinedMetricSpecification": {
      "PredefinedMetricType": "ECSServiceAverageMemoryUtilization"
    },
    "ScaleInCooldown": 300,
    "ScaleOutCooldown": 60
  }' \
  --region "$AWS_REGION" \
  2>/dev/null || echo "   Policy may already exist"

echo ""
echo "✅ Auto-scaling configured!"
echo ""
echo "📊 Auto-scaling settings:"
echo "   - Min capacity: 1 task"
echo "   - Max capacity: 5 tasks"
echo "   - Target CPU: 70%"
echo "   - Target Memory: 80%"
echo ""
echo "💡 Monitor scaling:"
echo "   aws ecs describe-services --cluster $CLUSTER_NAME --services $API_SERVICE --region $AWS_REGION --query 'services[0].{Desired:desiredCount,Running:runningCount}'"
echo ""
echo "📈 View auto-scaling:"
echo "   https://console.aws.amazon.com/ecs/v2/clusters/${CLUSTER_NAME}/services/${API_SERVICE}/auto-scaling?region=${AWS_REGION}"

