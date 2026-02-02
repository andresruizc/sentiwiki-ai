#!/bin/bash
# Force redeploy an ECS service (useful after adding IAM permissions)

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
SERVICE_NAME=${1:-"esa-iagen-api-service"}
TASK_DEF_SPECIFIED=${2:-""}
REGION=$AWS_REGION

echo "🔄 Forcing new deployment for ECS service..."
echo "   Cluster: $CLUSTER"
echo "   Service: $SERVICE_NAME"
echo "   Region: $REGION"
echo ""

# If task definition is specified, use it; otherwise get the latest revision
if [ -n "$TASK_DEF_SPECIFIED" ]; then
  TASK_DEF_TO_USE="$TASK_DEF_SPECIFIED"
  echo "📝 Using specified task definition: $TASK_DEF_TO_USE"
else
  # Get current task definition family
  CURRENT_TASK_DEF=$(aws ecs describe-services \
    --cluster $CLUSTER \
    --services $SERVICE_NAME \
    --region $REGION \
    --query 'services[0].taskDefinition' \
    --output text 2>/dev/null || echo "")
  
  if [ -n "$CURRENT_TASK_DEF" ] && [ "$CURRENT_TASK_DEF" != "None" ]; then
    # Get latest revision of the same family
    TASK_DEF_FAMILY=$(echo "$CURRENT_TASK_DEF" | grep -oE 'task-definition/[^:]+' | cut -d'/' -f2 || echo "")
    if [ -n "$TASK_DEF_FAMILY" ]; then
      LATEST_TASK_DEF=$(aws ecs describe-task-definition \
        --task-definition "$TASK_DEF_FAMILY" \
        --region $REGION \
        --query 'taskDefinition.taskDefinitionArn' \
        --output text 2>/dev/null || echo "")
      
      if [ -n "$LATEST_TASK_DEF" ] && [ "$LATEST_TASK_DEF" != "None" ]; then
        LATEST_REVISION=$(echo "$LATEST_TASK_DEF" | grep -oE '[0-9]+$' || echo "")
        TASK_DEF_TO_USE="${TASK_DEF_FAMILY}:${LATEST_REVISION}"
        CURRENT_REVISION=$(echo "$CURRENT_TASK_DEF" | grep -oE '[0-9]+$' || echo "")
        
        if [ "$CURRENT_REVISION" != "$LATEST_REVISION" ]; then
          echo "📝 Updating from revision $CURRENT_REVISION to latest revision $LATEST_REVISION"
        else
          echo "📝 Service already using latest revision ($LATEST_REVISION), forcing redeployment anyway"
        fi
      else
        TASK_DEF_TO_USE=""
      fi
    else
      TASK_DEF_TO_USE=""
    fi
  else
    TASK_DEF_TO_USE=""
  fi
fi

echo ""

# Force new deployment
echo "📤 Triggering new deployment..."
if [ -n "$TASK_DEF_TO_USE" ]; then
  aws ecs update-service \
    --cluster $CLUSTER \
    --service $SERVICE_NAME \
    --task-definition "$TASK_DEF_TO_USE" \
    --force-new-deployment \
    --region $REGION \
    --query 'service.serviceName' \
    --output text
else
  aws ecs update-service \
    --cluster $CLUSTER \
    --service $SERVICE_NAME \
    --force-new-deployment \
    --region $REGION \
    --query 'service.serviceName' \
    --output text
fi

echo ""
echo "✅ New deployment triggered!"
echo ""
echo "⏳ Waiting for service to stabilize (this may take 1-2 minutes)..."
echo ""

# Wait a bit for the deployment to start
sleep 5

# Check deployment status
echo "📊 Checking deployment status..."
aws ecs describe-services \
  --cluster $CLUSTER \
  --services $SERVICE_NAME \
  --region $REGION \
  --query 'services[0].deployments[0]' \
  --output table

echo ""
echo "💡 To check if tasks are running:"
echo "   aws ecs list-tasks --cluster $CLUSTER --service-name $SERVICE_NAME --region $REGION"
echo ""
echo "💡 To check service events:"
echo "   aws ecs describe-services --cluster $CLUSTER --services $SERVICE_NAME --region $REGION --query 'services[0].events[:5]' --output table"
echo ""
echo "💡 To check service status:"
echo "   cd deployment/aws/scripts && ./check-service-status.sh"

