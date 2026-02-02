#!/bin/bash
# Comprehensive diagnostic for API routing issues through ALB

set -e
export AWS_PAGER=""

# Load configuration
if [ ! -f "../infrastructure-ids.txt" ]; then
  echo "❌ infrastructure-ids.txt not found. Run setup-infrastructure.sh first."
  exit 1
fi

source ../infrastructure-ids.txt

CLUSTER="esa-iagen-cluster"
REGION=$AWS_REGION

echo "🔍 Comprehensive API Routing Diagnostic"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   ALB DNS: $ALB_DNS_NAME"
echo "   Region: $REGION"
echo ""

# 1. Check ALB status
echo "1️⃣  Checking ALB status..."
ALB_STATE=$(aws elbv2 describe-load-balancers \
  --load-balancer-arns $ALB_ARN \
  --region $REGION \
  --query 'LoadBalancers[0].State.Code' \
  --output text 2>/dev/null || echo "UNKNOWN")

if [ "$ALB_STATE" = "active" ]; then
  echo "   ✅ ALB is active"
else
  echo "   ❌ ALB state: $ALB_STATE"
fi

# 2. Check listener rules
echo ""
echo "2️⃣  Checking ALB listener rules..."
LISTENER_ARN=$(aws elbv2 describe-listeners \
  --load-balancer-arn $ALB_ARN \
  --region $REGION \
  --query 'Listeners[?Port==`80`].ListenerArn' \
  --output text 2>/dev/null || echo "")

if [ -z "$LISTENER_ARN" ] || [ "$LISTENER_ARN" = "None" ]; then
  echo "   ❌ No listener found"
  exit 1
fi

echo "   ✅ Listener: $LISTENER_ARN"

# Get all rules
RULES_JSON=$(aws elbv2 describe-rules \
  --listener-arn $LISTENER_ARN \
  --region $REGION \
  --output json)

API_RULE=$(echo "$RULES_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for rule in data.get('Rules', []):
    if rule.get('Priority') != 'default':
        for condition in rule.get('Conditions', []):
            if condition.get('Field') == 'path-pattern':
                values = condition.get('PathPatternConfig', {}).get('Values', [])
                if '/api/*' in values:
                    print(rule.get('RuleArn', ''))
                    break
" 2>/dev/null || echo "")

if [ -n "$API_RULE" ] && [ "$API_RULE" != "None" ]; then
  echo "   ✅ API rule exists: $API_RULE"
else
  echo "   ❌ API rule (/api/*) not found!"
fi

# 3. Check target group health
echo ""
echo "3️⃣  Checking target group health..."
TG_HEALTH=$(aws elbv2 describe-target-health \
  --target-group-arn $TARGET_GROUP_ARN \
  --region $REGION \
  --output json)

HEALTHY_COUNT=$(echo "$TG_HEALTH" | python3 -c "
import sys, json
data = json.load(sys.stdin)
healthy = sum(1 for t in data.get('TargetHealthDescriptions', []) if t.get('TargetHealth', {}).get('State') == 'healthy')
print(healthy)
" 2>/dev/null || echo "0")

TOTAL_COUNT=$(echo "$TG_HEALTH" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(len(data.get('TargetHealthDescriptions', [])))
" 2>/dev/null || echo "0")

echo "   Targets: $HEALTHY_COUNT/$TOTAL_COUNT healthy"

if [ "$HEALTHY_COUNT" -eq 0 ]; then
  echo "   ❌ No healthy targets! This is likely the problem."
  echo ""
  echo "   Target health details:"
  echo "$TG_HEALTH" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for t in data.get('TargetHealthDescriptions', []):
    target_id = t.get('Target', {}).get('Id', 'unknown')
    state = t.get('TargetHealth', {}).get('State', 'unknown')
    reason = t.get('TargetHealth', {}).get('Reason', '')
    print(f'      {target_id}: {state} ({reason})')
" 2>/dev/null || echo "      Could not parse health details"
fi

# 4. Check target group health check path
echo ""
echo "4️⃣  Checking target group health check configuration..."
TG_CONFIG=$(aws elbv2 describe-target-groups \
  --target-group-arns $TARGET_GROUP_ARN \
  --region $REGION \
  --output json)

HEALTH_PATH=$(echo "$TG_CONFIG" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('TargetGroups', [{}])[0].get('HealthCheckPath', ''))
" 2>/dev/null || echo "")

echo "   Health check path: $HEALTH_PATH"
echo "   Health check port: $(echo "$TG_CONFIG" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('TargetGroups', [{}])[0].get('HealthCheckPort', ''))" 2>/dev/null || echo '')"

# FastAPI has /health endpoint, but ALB routes /api/* to API
# So health check should be /api/health OR we need a separate rule for /health
if [ "$HEALTH_PATH" = "/health" ]; then
  echo "   ⚠️  Health check uses /health (doesn't match /api/* rule)"
  echo "      This might cause health checks to fail or route incorrectly"
fi

# 5. Check API service status
echo ""
echo "5️⃣  Checking API service status..."
API_SERVICE=$(aws ecs describe-services \
  --cluster $CLUSTER \
  --services esa-iagen-api-service \
  --region $REGION \
  --output json)

RUNNING_COUNT=$(echo "$API_SERVICE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
service = data.get('services', [{}])[0]
print(service.get('runningCount', 0))
" 2>/dev/null || echo "0")

DESIRED_COUNT=$(echo "$API_SERVICE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
service = data.get('services', [{}])[0]
print(service.get('desiredCount', 0))
" 2>/dev/null || echo "0")

echo "   Running: $RUNNING_COUNT/$DESIRED_COUNT tasks"

if [ "$RUNNING_COUNT" -eq 0 ]; then
  echo "   ❌ No running tasks! Check service events:"
  echo "$API_SERVICE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
service = data.get('services', [{}])[0]
for event in service.get('events', [])[:5]:
    print(f'      {event.get(\"createdAt\", \"\")}: {event.get(\"message\", \"\")}')
" 2>/dev/null || echo "      Could not parse events"
fi

# 6. Test connectivity
echo ""
echo "6️⃣  Testing connectivity..."

# Test direct API (if we can get the IP)
API_TASK=$(aws ecs list-tasks \
  --cluster $CLUSTER \
  --service-name esa-iagen-api-service \
  --desired-status RUNNING \
  --region $REGION \
  --query 'taskArns[0]' \
  --output text 2>/dev/null || echo "")

if [ -n "$API_TASK" ] && [ "$API_TASK" != "None" ]; then
  ENI_ID=$(aws ecs describe-tasks \
    --cluster $CLUSTER \
    --tasks $API_TASK \
    --region $REGION \
    --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' \
    --output text 2>/dev/null || echo "")
  
  if [ -n "$ENI_ID" ] && [ "$ENI_ID" != "None" ]; then
    API_IP=$(aws ec2 describe-network-interfaces \
      --network-interface-ids $ENI_ID \
      --region $REGION \
      --query 'NetworkInterfaces[0].Association.PublicIp' \
      --output text 2>/dev/null || echo "")
    
    if [ -n "$API_IP" ] && [ "$API_IP" != "None" ]; then
      echo "   API IP: $API_IP"
      
      echo "   Testing direct /health..."
      DIRECT_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://$API_IP:8000/health" 2>/dev/null || echo "000")
      if [ "$DIRECT_HEALTH" = "200" ]; then
        echo "   ✅ Direct /health works"
      else
        echo "   ❌ Direct /health failed (HTTP $DIRECT_HEALTH)"
      fi
      
      echo "   Testing direct /api/v1/chat..."
      DIRECT_CHAT=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "http://$API_IP:8000/api/v1/chat?query=test" 2>/dev/null || echo "000")
      if [ "$DIRECT_CHAT" = "200" ] || [ "$DIRECT_CHAT" = "400" ]; then
        echo "   ✅ Direct /api/v1/chat works (HTTP $DIRECT_CHAT)"
      else
        echo "   ❌ Direct /api/v1/chat failed (HTTP $DIRECT_CHAT)"
      fi
    fi
  fi
fi

# Test through ALB
echo ""
echo "   Testing through ALB..."
echo "   Testing: http://$ALB_DNS_NAME/api/health"
ALB_HEALTH=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "http://$ALB_DNS_NAME/api/health" 2>/dev/null || echo "000")
if [ "$ALB_HEALTH" = "200" ]; then
  echo "   ✅ ALB /api/health works"
else
  echo "   ❌ ALB /api/health failed (HTTP $ALB_HEALTH)"
fi

echo "   Testing: http://$ALB_DNS_NAME/api/v1/chat?query=test"
ALB_CHAT=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "http://$ALB_DNS_NAME/api/v1/chat?query=test" 2>/dev/null || echo "000")
if [ "$ALB_CHAT" = "200" ] || [ "$ALB_CHAT" = "400" ]; then
  echo "   ✅ ALB /api/v1/chat works (HTTP $ALB_CHAT)"
else
  echo "   ❌ ALB /api/v1/chat failed (HTTP $ALB_CHAT)"
fi

# Summary
echo ""
echo "=============================================="
echo "📋 Summary & Recommendations"
echo "=============================================="
echo ""

if [ "$HEALTHY_COUNT" -eq 0 ]; then
  echo "❌ CRITICAL: No healthy targets in target group"
  echo ""
  echo "   Fix: Update target group health check path"
  echo "   Current: $HEALTH_PATH"
  echo "   FastAPI has: /health endpoint"
  echo ""
  echo "   Options:"
  echo "   1. Change health check to /api/health (if FastAPI handles it)"
  echo "   2. Add ALB rule: /health → API target group"
  echo "   3. Update FastAPI to add /api/health endpoint"
  echo ""
fi

if [ "$RUNNING_COUNT" -eq 0 ]; then
  echo "❌ CRITICAL: No running API tasks"
  echo ""
  echo "   Fix: Check service events and logs"
  echo "   Run: aws ecs describe-services --cluster $CLUSTER --services esa-iagen-api-service --region $REGION"
  echo ""
fi

if [ "$ALB_HEALTH" != "200" ] && [ "$ALB_CHAT" != "200" ] && [ "$ALB_CHAT" != "400" ]; then
  echo "❌ ALB routing is not working"
  echo ""
  echo "   Possible causes:"
  echo "   1. Target group has no healthy targets"
  echo "   2. ALB rule /api/* is missing or incorrect"
  echo "   3. Security group blocking traffic"
  echo "   4. API service is not running"
  echo ""
fi

echo "🔧 Quick fixes to try:"
echo "   1. Run: ./fix-alb-api-routing.sh"
echo "   2. Check API logs: aws logs tail /ecs/esa-iagen --follow --region $REGION | grep api"
echo "   3. Verify security groups allow port 8000"
echo ""

