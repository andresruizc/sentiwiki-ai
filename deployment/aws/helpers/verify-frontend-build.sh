#!/bin/bash
# Verify if frontend image was built with ALB URL
# This script checks multiple indicators to determine if the build included the ALB URL

set -e

export AWS_PAGER=""

# Load configuration
if [ ! -f "../infrastructure-ids.txt" ]; then
  echo "❌ infrastructure-ids.txt not found. Run setup-infrastructure.sh first."
  exit 1
fi

source ../infrastructure-ids.txt

echo "🔍 Verifying Frontend Build Configuration"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 1. Check when image was last built
echo "1️⃣  Checking Frontend Image in ECR..."
LATEST_IMAGE=$(aws ecr describe-images \
  --repository-name esa-iagen-frontend \
  --region $AWS_REGION \
  --query 'sort_by(imageDetails, &imagePushedAt)[-1]' \
  --output json 2>/dev/null || echo "{}")

PUSHED_AT=$(echo "$LATEST_IMAGE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('imagePushedAt', 'Unknown'))" 2>/dev/null || echo "Unknown")
IMAGE_TAGS=$(echo "$LATEST_IMAGE" | python3 -c "import sys, json; data=json.load(sys.stdin); print(', '.join(data.get('imageTags', [])))" 2>/dev/null || echo "Unknown")

echo "   Latest image pushed at: $PUSHED_AT"
echo "   Tags: $IMAGE_TAGS"
echo ""

# 2. Check when ALB was created
echo "2️⃣  Checking ALB Creation Time..."
ALB_CREATED=$(aws elbv2 describe-load-balancers \
  --load-balancer-arns $ALB_ARN \
  --region $AWS_REGION \
  --query 'LoadBalancers[0].CreatedTime' \
  --output text 2>/dev/null || echo "Unknown")

echo "   ALB created at: $ALB_CREATED"
echo ""

# 3. Compare timestamps
echo "3️⃣  Build vs ALB Timeline..."
if [ "$PUSHED_AT" != "Unknown" ] && [ "$ALB_CREATED" != "Unknown" ]; then
  # Convert to comparable format (simplified check)
  echo "   ⚠️  If image was built BEFORE ALB was created, it would have used localhost:8002"
  echo "   💡 Check GitHub Actions logs to see if ALB DNS was found during build"
fi
echo ""

# 4. Check current task definition
echo "4️⃣  Checking Current Task Definition..."
TASK_DEF=$(aws ecs describe-task-definition \
  --task-definition esa-iagen-frontend \
  --region $AWS_REGION \
  --query 'taskDefinition.containerDefinitions[0]' \
  --output json 2>/dev/null || echo "{}")

ENV_API_URL=$(echo "$TASK_DEF" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for env in data.get('environment', []):
    if env.get('name') == 'NEXT_PUBLIC_API_URL':
        print(env.get('value', 'Not set'))
        break
else:
    print('Not set in task definition')
" 2>/dev/null || echo "Error reading")

echo "   NEXT_PUBLIC_API_URL in task definition: $ENV_API_URL"
echo "   ⚠️  NOTE: This env var is IGNORED by Next.js at runtime!"
echo "   Next.js only reads NEXT_PUBLIC_* vars at BUILD TIME"
echo ""

# 5. Check running task
echo "5️⃣  Checking Running Frontend Task..."
TASK_ARN=$(aws ecs list-tasks \
  --cluster esa-iagen-cluster \
  --service-name esa-iagen-frontend-service \
  --desired-status RUNNING \
  --region $AWS_REGION \
  --query 'taskArns[0]' \
  --output text 2>/dev/null || echo "")

if [ -n "$TASK_ARN" ] && [ "$TASK_ARN" != "None" ]; then
  TASK_IMAGE=$(aws ecs describe-tasks \
    --cluster esa-iagen-cluster \
    --tasks $TASK_ARN \
    --region $AWS_REGION \
    --query 'tasks[0].containers[0].image' \
    --output text 2>/dev/null || echo "Unknown")
  
  TASK_STARTED=$(aws ecs describe-tasks \
    --cluster esa-iagen-cluster \
    --tasks $TASK_ARN \
    --region $AWS_REGION \
    --query 'tasks[0].startedAt' \
    --output text 2>/dev/null || echo "Unknown")
  
  echo "   Task image: $TASK_IMAGE"
  echo "   Task started: $TASK_STARTED"
  echo "   ✅ Task is running"
else
  echo "   ❌ No running tasks found"
fi
echo ""

# 6. Recommendations
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 Diagnosis & Recommendations"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

echo "🔍 To verify what URL is actually in the bundle:"
echo "   1. Open frontend in browser: http://13.53.200.78:3000"
echo "   2. Open browser console (F12)"
echo "   3. Look for log: '📍 API URL: ...'"
echo "   4. Check Network tab - see what URL requests are going to"
echo ""

echo "✅ If the console shows 'localhost:8002', the image needs to be rebuilt:"
echo "   1. Check GitHub Actions logs for 'push-frontend' job"
echo "   2. Look for: '✅ Found ALB: esa-iagen-api-alb-...'"
echo "   3. If it shows '⚠️ ALB not found', the build used localhost:8002"
echo ""

echo "🔧 Solutions:"
echo ""
echo "   Option A: Rebuild with ALB URL (if build failed to get ALB)"
echo "   - Make a new commit to trigger CI/CD"
echo "   - Ensure ALB exists before build runs"
echo "   - Force frontend redeploy after new image is pushed"
echo ""
echo "   Option B: Use runtime config (more robust)"
echo "   - Re-implement runtime config system"
echo "   - Generate config file at container startup"
echo "   - Read from task definition env var at runtime"
echo ""

echo "💡 Quick Test:"
echo "   Open browser console and type:"
echo "   console.log('API URL:', process.env.NEXT_PUBLIC_API_URL)"
echo "   This will show what's actually in the bundle"

