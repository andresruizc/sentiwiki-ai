#!/bin/bash
# Diagnostic script specifically for frontend service health issues

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
SERVICE_NAME="esa-iagen-frontend-service"
REGION=$AWS_REGION

echo "🔍 Diagnosing Frontend Service Health Issues..."
echo "   Cluster: $CLUSTER"
echo "   Service: $SERVICE_NAME"
echo "   Region: $REGION"
echo ""

# 1. Check service status
echo "1️⃣  Service Status:"
SERVICE_INFO=$(aws ecs describe-services \
  --cluster $CLUSTER \
  --services $SERVICE_NAME \
  --region $REGION \
  --query 'services[0]' \
  --output json)

echo "$SERVICE_INFO" | jq -r '
  "   Status: " + .status,
  "   Desired: " + (.desiredCount | tostring),
  "   Running: " + (.runningCount | tostring),
  "   Pending: " + (.pendingCount | tostring)
'
echo ""

# 2. Check recent events
echo "2️⃣  Recent Service Events (last 5):"
aws ecs describe-services \
  --cluster $CLUSTER \
  --services $SERVICE_NAME \
  --region $REGION \
  --query 'services[0].events[:5]' \
  --output table
echo ""

# 3. Get running task details
echo "3️⃣  Running Task Details:"
TASK_ARN=$(aws ecs list-tasks \
  --cluster $CLUSTER \
  --service-name $SERVICE_NAME \
  --region $REGION \
  --query 'taskArns[0]' \
  --output text 2>/dev/null || echo "")

if [ -z "$TASK_ARN" ] || [ "$TASK_ARN" = "None" ] || [ "$TASK_ARN" = "null" ]; then
  echo "   ⚠️  No running tasks found"
else
  echo "   Task ARN: $TASK_ARN"
  
  # Get task details
  TASK_INFO=$(aws ecs describe-tasks \
    --cluster $CLUSTER \
    --tasks $TASK_ARN \
    --region $REGION \
    --query 'tasks[0]' \
    --output json)
  
  # Health status
  HEALTH_STATUS=$(echo "$TASK_INFO" | jq -r '.healthStatus // "UNKNOWN"')
  LAST_STATUS=$(echo "$TASK_INFO" | jq -r '.lastStatus // "UNKNOWN"')
  
  echo "   Health Status: $HEALTH_STATUS"
  echo "   Last Status: $LAST_STATUS"
  
  # Container health
  CONTAINER_HEALTH=$(echo "$TASK_INFO" | jq -r '.containers[0].healthStatus // "UNKNOWN"')
  echo "   Container Health: $CONTAINER_HEALTH"
  
  # Get public IP
  ENI_ID=$(echo "$TASK_INFO" | jq -r '.attachments[0].details[] | select(.name=="networkInterfaceId") | .value' 2>/dev/null || echo "")
  if [ -n "$ENI_ID" ] && [ "$ENI_ID" != "null" ]; then
    PUBLIC_IP=$(aws ec2 describe-network-interfaces \
      --network-interface-ids $ENI_ID \
      --region $REGION \
      --query 'NetworkInterfaces[0].Association.PublicIp' \
      --output text 2>/dev/null || echo "")
    if [ -n "$PUBLIC_IP" ] && [ "$PUBLIC_IP" != "None" ]; then
      echo "   Public IP: $PUBLIC_IP"
      echo "   URL: http://$PUBLIC_IP:3000"
    fi
  fi
fi
echo ""

# 4. Check stopped tasks for errors
echo "4️⃣  Recently Stopped Tasks (last 3):"
STOPPED_TASKS=$(aws ecs list-tasks \
  --cluster $CLUSTER \
  --service-name $SERVICE_NAME \
  --desired-status STOPPED \
  --region $REGION \
  --query 'taskArns[:3]' \
  --output text 2>/dev/null || echo "")

if [ -n "$STOPPED_TASKS" ] && [ "$STOPPED_TASKS" != "None" ]; then
  for TASK_ARN in $STOPPED_TASKS; do
    echo ""
    echo "   Task: $(echo $TASK_ARN | cut -d'/' -f3)"
    STOPPED_REASON=$(aws ecs describe-tasks \
      --cluster $CLUSTER \
      --tasks $TASK_ARN \
      --region $REGION \
      --query 'tasks[0].stoppedReason' \
      --output text 2>/dev/null || echo "Unknown")
    echo "   Stopped Reason: $STOPPED_REASON"
    
    EXIT_CODE=$(aws ecs describe-tasks \
      --cluster $CLUSTER \
      --tasks $TASK_ARN \
      --region $REGION \
      --query 'tasks[0].containers[0].exitCode' \
      --output text 2>/dev/null || echo "Unknown")
    echo "   Exit Code: $EXIT_CODE"
  done
else
  echo "   No stopped tasks found"
fi
echo ""

# 5. Check health check configuration
echo "5️⃣  Health Check Configuration:"
TASK_DEF=$(aws ecs describe-services \
  --cluster $CLUSTER \
  --services $SERVICE_NAME \
  --region $REGION \
  --query 'services[0].taskDefinition' \
  --output text)

HEALTH_CHECK=$(aws ecs describe-task-definition \
  --task-definition $TASK_DEF \
  --region $REGION \
  --query 'taskDefinition.containerDefinitions[0].healthCheck' \
  --output json)

echo "$HEALTH_CHECK" | jq '.'
echo ""

# 6. Check recent logs
echo "6️⃣  Recent Logs (last 20 lines):"
echo "   (This may take a moment...)"
aws logs tail /ecs/esa-iagen \
  --filter-pattern "frontend" \
  --since 10m \
  --region $REGION 2>/dev/null | tail -20 || echo "   ⚠️  Could not retrieve logs"
echo ""

# 7. Test if frontend is accessible (if we have an IP)
if [ -n "$PUBLIC_IP" ] && [ "$PUBLIC_IP" != "None" ]; then
  echo "7️⃣  Testing Frontend Accessibility:"
  echo "   Testing: http://$PUBLIC_IP:3000"
  
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://$PUBLIC_IP:3000" 2>/dev/null || echo "000")
  
  if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "301" ] || [ "$HTTP_CODE" = "302" ]; then
    echo "   ✅ Frontend is accessible (HTTP $HTTP_CODE)"
  else
    echo "   ❌ Frontend is NOT accessible (HTTP $HTTP_CODE)"
    echo "   This could mean:"
    echo "   - Container is not running"
    echo "   - Port 3000 is not listening"
    echo "   - Security group blocking traffic"
  fi
else
  echo "7️⃣  Cannot test accessibility (no public IP found)"
fi
echo ""

# Summary and recommendations
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📋 Summary and Recommendations:"
echo ""

if [ "$HEALTH_STATUS" = "UNHEALTHY" ] || [ "$CONTAINER_HEALTH" = "UNHEALTHY" ]; then
  echo "❌ Frontend is UNHEALTHY"
  echo ""
  echo "Common causes:"
  echo "1. Health check command failing (wget might not be installed)"
  echo "2. Frontend taking longer than 40 seconds to start"
  echo "3. Frontend crashing after startup"
  echo "4. Port 3000 not listening"
  echo ""
  echo "Solutions:"
  echo "1. Check if wget is available in the container"
  echo "2. Increase startPeriod in health check (currently 40s)"
  echo "3. Change health check to use curl instead of wget"
  echo "4. Check logs for startup errors"
  echo ""
  echo "Quick fix - Update health check to use curl:"
  echo "   Edit aws/task-definitions/task-frontend.json"
  echo "   Change health check command to:"
  echo "   \"curl -f http://localhost:3000 || exit 1\""
  echo ""
  echo "Then run:"
  echo "   cd deployment/aws/scripts && ./register-task-definitions.sh"
  echo "   aws ecs update-service --cluster $CLUSTER --service $SERVICE_NAME --force-new-deployment --region $REGION"
elif [ "$HEALTH_STATUS" = "HEALTHY" ] || [ "$CONTAINER_HEALTH" = "HEALTHY" ]; then
  echo "✅ Frontend appears to be HEALTHY"
  echo ""
  if [ -n "$PUBLIC_IP" ] && [ "$PUBLIC_IP" != "None" ]; then
    echo "Access your frontend at: http://$PUBLIC_IP:3000"
  fi
else
  echo "⚠️  Frontend status is unclear. Check the details above."
fi

