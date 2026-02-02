#!/bin/bash
# Diagnostic script to check why a service isn't running

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
SERVICE_NAME="esa-iagen-api-service"
REGION=$AWS_REGION

echo "🔍 Diagnosing API service status..."
echo "   Cluster: $CLUSTER"
echo "   Service: $SERVICE_NAME"
echo "   Region: $REGION"
echo ""

# 1. Check if service exists
echo "1️⃣  Checking if service exists..."
SERVICE_EXISTS=$(aws ecs describe-services \
  --cluster $CLUSTER \
  --services $SERVICE_NAME \
  --region $REGION \
  --query 'services[0].serviceName' \
  --output text 2>/dev/null || echo "NOT_FOUND")

if [ "$SERVICE_EXISTS" = "NOT_FOUND" ] || [ -z "$SERVICE_EXISTS" ] || [ "$SERVICE_EXISTS" = "None" ]; then
  echo "   ❌ Service does NOT exist!"
  echo ""
  echo "   💡 Solution: Run create-services.sh to create the service"
  echo "      cd aws/scripts && ./create-services.sh"
  exit 1
fi

echo "   ✅ Service exists"
echo ""

# 2. Check service status
echo "2️⃣  Checking service status..."
SERVICE_STATUS=$(aws ecs describe-services \
  --cluster $CLUSTER \
  --services $SERVICE_NAME \
  --region $REGION \
  --query 'services[0].status' \
  --output text)

DESIRED_COUNT=$(aws ecs describe-services \
  --cluster $CLUSTER \
  --services $SERVICE_NAME \
  --region $REGION \
  --query 'services[0].desiredCount' \
  --output text)

RUNNING_COUNT=$(aws ecs describe-services \
  --cluster $CLUSTER \
  --services $SERVICE_NAME \
  --region $REGION \
  --query 'services[0].runningCount' \
  --output text)

PENDING_COUNT=$(aws ecs describe-services \
  --cluster $CLUSTER \
  --services $SERVICE_NAME \
  --region $REGION \
  --query 'services[0].pendingCount' \
  --output text)

echo "   Status: $SERVICE_STATUS"
echo "   Desired tasks: $DESIRED_COUNT"
echo "   Running tasks: $RUNNING_COUNT"
echo "   Pending tasks: $PENDING_COUNT"
echo ""

# 3. Check service events (recent errors)
echo "3️⃣  Recent service events (last 5):"
aws ecs describe-services \
  --cluster $CLUSTER \
  --services $SERVICE_NAME \
  --region $REGION \
  --query 'services[0].events[:5]' \
  --output table

echo ""

# 4. Check task definition
echo "4️⃣  Checking task definition..."
TASK_DEF=$(aws ecs describe-services \
  --cluster $CLUSTER \
  --services $SERVICE_NAME \
  --region $REGION \
  --query 'services[0].taskDefinition' \
  --output text)

echo "   Task Definition: $TASK_DEF"

# Check if task definition exists
TASK_DEF_EXISTS=$(aws ecs describe-task-definition \
  --task-definition $TASK_DEF \
  --region $REGION \
  --query 'taskDefinition.taskDefinitionArn' \
  --output text 2>/dev/null || echo "NOT_FOUND")

if [ "$TASK_DEF_EXISTS" = "NOT_FOUND" ]; then
  echo "   ❌ Task definition does NOT exist!"
  echo ""
  echo "   💡 Solution: Run register-task-definitions.sh"
  echo "      cd aws/scripts && ./register-task-definitions.sh"
  exit 1
fi

echo "   ✅ Task definition exists"
echo ""

# 5. Check ECR image
echo "5️⃣  Checking ECR image..."
IMAGE_URI=$(aws ecs describe-task-definition \
  --task-definition $TASK_DEF \
  --region $REGION \
  --query 'taskDefinition.containerDefinitions[0].image' \
  --output text)

echo "   Image URI: $IMAGE_URI"

# Extract repository name
REPO_NAME=$(echo $IMAGE_URI | cut -d'/' -f2 | cut -d':' -f1)
IMAGE_TAG=$(echo $IMAGE_URI | cut -d':' -f2)

echo "   Repository: $REPO_NAME"
echo "   Tag: $IMAGE_TAG"

# Check if image exists in ECR
IMAGE_EXISTS=$(aws ecr describe-images \
  --repository-name $REPO_NAME \
  --image-ids imageTag=$IMAGE_TAG \
  --region $REGION \
  --query 'imageDetails[0].imageTags[0]' \
  --output text 2>/dev/null || echo "NOT_FOUND")

if [ "$IMAGE_EXISTS" = "NOT_FOUND" ]; then
  echo "   ❌ Image does NOT exist in ECR!"
  echo ""
  echo "   💡 Solution: Push image to ECR via GitHub Actions (Phase 3)"
  echo "      Or manually: docker push $IMAGE_URI"
  exit 1
fi

echo "   ✅ Image exists in ECR"
echo ""

# 6. Check stopped tasks (if any)
echo "6️⃣  Checking stopped tasks (last 3) for errors..."
STOPPED_TASKS=$(aws ecs list-tasks \
  --cluster $CLUSTER \
  --service-name $SERVICE_NAME \
  --desired-status STOPPED \
  --region $REGION \
  --query 'taskArns[:3]' \
  --output text)

if [ -n "$STOPPED_TASKS" ] && [ "$STOPPED_TASKS" != "None" ]; then
  for TASK_ARN in $STOPPED_TASKS; do
    echo ""
    echo "   Task: $TASK_ARN"
    STOPPED_REASON=$(aws ecs describe-tasks \
      --cluster $CLUSTER \
      --tasks $TASK_ARN \
      --region $REGION \
      --query 'tasks[0].stoppedReason' \
      --output text)
    echo "   Stopped reason: $STOPPED_REASON"
    
    # Get exit code
    EXIT_CODE=$(aws ecs describe-tasks \
      --cluster $CLUSTER \
      --tasks $TASK_ARN \
      --region $REGION \
      --query 'tasks[0].containers[0].exitCode' \
      --output text)
    echo "   Exit code: $EXIT_CODE"
  done
else
  echo "   No stopped tasks found"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Summary
if [ "$RUNNING_COUNT" -eq 0 ] && [ "$PENDING_COUNT" -eq 0 ]; then
  echo "❌ Service is not running and no tasks are pending"
  echo ""
  echo "Common causes:"
  echo "1. Task definition image doesn't exist in ECR"
  echo "2. Task failed to start (check stopped tasks above)"
  echo "3. IAM role permissions issue"
  echo "4. Security group blocking traffic"
  echo "5. Secrets Manager secrets not configured"
  echo ""
  echo "Next steps:"
  echo "1. Check the 'Stopped reason' above for specific errors"
  echo "2. Check CloudWatch Logs:"
  echo "   aws logs tail /ecs/esa-iagen-api --follow --region $REGION"
  echo "3. Try updating the service to force a new deployment:"
  echo "   aws ecs update-service --cluster $CLUSTER --service $SERVICE_NAME --force-new-deployment --region $REGION"
else
  echo "✅ Service appears to be running or starting"
  echo "   Running: $RUNNING_COUNT, Pending: $PENDING_COUNT"
fi

