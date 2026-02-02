#!/bin/bash
# Comprehensive diagnostic script for ALB-Frontend connection issues
# Checks Security Groups, ALB, Target Group, CORS, and connectivity

set -e

# Disable AWS CLI pager
export AWS_PAGER=""

# Load configuration
if [ ! -f "../infrastructure-ids.txt" ]; then
  echo "❌ infrastructure-ids.txt not found. Run setup-infrastructure.sh first."
  exit 1
fi

source ../infrastructure-ids.txt

CLUSTER="esa-iagen-cluster"
REGION=$AWS_REGION

echo "🔍 Comprehensive ALB-Frontend Connection Diagnostic"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "   Region: $REGION"
echo "   ALB DNS: $ALB_DNS_NAME"
echo ""

# 1. Check ALB Status
echo "1️⃣  Checking ALB Status..."
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

# 2. Check ALB Security Group
echo ""
echo "2️⃣  Checking ALB Security Group..."
ALB_SG=$(aws elbv2 describe-load-balancers \
  --load-balancer-arns $ALB_ARN \
  --region $REGION \
  --query 'LoadBalancers[0].SecurityGroups[0]' \
  --output text 2>/dev/null || echo "")

if [ -n "$ALB_SG" ] && [ "$ALB_SG" != "None" ]; then
  echo "   ✅ ALB Security Group: $ALB_SG"
  
  # Check ALB SG rules
  echo "   Checking ALB Security Group rules (inbound)..."
  ALB_SG_RULES=$(aws ec2 describe-security-groups \
    --group-ids $ALB_SG \
    --region $REGION \
    --query 'SecurityGroups[0].IpPermissions' \
    --output json 2>/dev/null || echo "[]")
  
  # Check for port 80 rule
  HAS_PORT_80=$(echo "$ALB_SG_RULES" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for rule in data:
    if rule.get('FromPort') == 80 or rule.get('ToPort') == 80:
        if 'IpRanges' in rule:
            for ip_range in rule['IpRanges']:
                if ip_range.get('CidrIp') == '0.0.0.0/0':
                    print('true')
                    sys.exit(0)
print('false')
" 2>/dev/null || echo "false")
  
  if [ "$HAS_PORT_80" = "true" ]; then
    echo "      ✅ Port 80 allowed from 0.0.0.0/0 (Internet → ALB)"
  else
    echo "      ❌ Port 80 NOT allowed from Internet"
    echo "      🔧 FIX: Add rule to allow port 80 from 0.0.0.0/0"
  fi
else
  echo "   ❌ ALB has no security group!"
fi

# 3. Check API Security Group
echo ""
echo "3️⃣  Checking API Security Group..."
echo "   API Security Group: $SECURITY_GROUP_ID"

# Check if API SG allows traffic from ALB SG
API_SG_RULES=$(aws ec2 describe-security-groups \
  --group-ids $SECURITY_GROUP_ID \
  --region $REGION \
  --query 'SecurityGroups[0].IpPermissions' \
  --output json 2>/dev/null || echo "[]")

# Check for port 8000 from ALB SG
HAS_ALB_TO_API=$(echo "$API_SG_RULES" | python3 -c "
import sys, json
data = json.load(sys.stdin)
alb_sg = '$ALB_SG'
api_sg = '$SECURITY_GROUP_ID'

# First check if ALB and API use same SG (internal rule applies)
if alb_sg == api_sg:
    # Check for internal rule (protocol -1 from same SG)
    for rule in data:
        if rule.get('IpProtocol') == '-1':
            if 'UserIdGroupPairs' in rule:
                for pair in rule['UserIdGroupPairs']:
                    if pair.get('GroupId') == api_sg:
                        print('same_sg')
                        sys.exit(0)
    # Also check for explicit port 8000 rule (from anywhere or same SG)
    for rule in data:
        if rule.get('FromPort') == 8000 or rule.get('ToPort') == 8000:
            # Check if from same SG
            if 'UserIdGroupPairs' in rule:
                for pair in rule['UserIdGroupPairs']:
                    if pair.get('GroupId') == api_sg:
                        print('same_sg')
                        sys.exit(0)
            # Check if from anywhere (0.0.0.0/0)
            if 'IpRanges' in rule:
                for ip_range in rule['IpRanges']:
                    if ip_range.get('CidrIp') == '0.0.0.0/0':
                        print('same_sg')
                        sys.exit(0)
else:
    # Different SGs - need explicit rule from ALB SG
    for rule in data:
        if rule.get('FromPort') == 8000 or rule.get('ToPort') == 8000:
            if 'UserIdGroupPairs' in rule:
                for pair in rule['UserIdGroupPairs']:
                    if pair.get('GroupId') == alb_sg:
                        print('true')
                        sys.exit(0)
print('false')
" 2>/dev/null || echo "false")

if [ "$HAS_ALB_TO_API" = "true" ]; then
  echo "      ✅ Port 8000 allowed from ALB Security Group"
elif [ "$HAS_ALB_TO_API" = "same_sg" ]; then
  echo "      ✅ Port 8000 allowed (ALB and API use same SG, internal rule applies)"
else
  echo "      ❌ Port 8000 NOT allowed from ALB Security Group"
  echo "      🔧 FIX: Add rule to allow port 8000 from ALB SG"
fi

# 4. Check Target Group Health
echo ""
echo "4️⃣  Checking Target Group Health..."
TARGET_HEALTH=$(aws elbv2 describe-target-health \
  --target-group-arn $TARGET_GROUP_ARN \
  --region $REGION \
  --query 'TargetHealthDescriptions[*].{Target:Target.Id,State:TargetHealth.State,Reason:TargetHealth.Reason}' \
  --output json 2>/dev/null || echo "[]")

HEALTHY_COUNT=$(echo "$TARGET_HEALTH" | python3 -c "
import sys, json
data = json.load(sys.stdin)
count = sum(1 for item in data if item.get('State') == 'healthy')
print(count)
" 2>/dev/null || echo "0")

TOTAL_COUNT=$(echo "$TARGET_HEALTH" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(len(data))
" 2>/dev/null || echo "0")

echo "$TARGET_HEALTH" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for item in data:
    target = item.get('Target', {}).get('Id', 'Unknown')
    state = item.get('State', 'Unknown')
    reason = item.get('Reason', 'N/A')
    status_icon = '✅' if state == 'healthy' else '❌'
    print(f'      {status_icon} Target {target}: {state} ({reason})')
" 2>/dev/null || echo "      ⚠️  Could not parse target health"

if [ "$HEALTHY_COUNT" -gt 0 ]; then
  echo "   ✅ $HEALTHY_COUNT/$TOTAL_COUNT targets are healthy"
else
  echo "   ❌ No healthy targets! ALB cannot route traffic"
  echo "   🔧 FIX: Check API service logs and health endpoint"
fi

# 5. Check CORS Configuration
echo ""
echo "5️⃣  Checking CORS Configuration..."
CURRENT_CORS=$(aws ecs describe-task-definition \
  --task-definition esa-iagen-api \
  --region $REGION \
  --query 'taskDefinition.containerDefinitions[0].environment[?name==`API__CORS_ORIGINS`].value' \
  --output text 2>/dev/null || echo "")

if [ -n "$CURRENT_CORS" ]; then
  echo "   Current CORS origins: $CURRENT_CORS"
  
  # Get current frontend IP
  FRONTEND_TASK_ARN=$(aws ecs list-tasks \
    --cluster $CLUSTER \
    --service-name esa-iagen-frontend-service \
    --desired-status RUNNING \
    --region $REGION \
    --query 'taskArns[0]' \
    --output text 2>/dev/null || echo "")
  
  if [ -n "$FRONTEND_TASK_ARN" ] && [ "$FRONTEND_TASK_ARN" != "None" ]; then
    ENI_ID=$(aws ecs describe-tasks \
      --cluster $CLUSTER \
      --tasks $FRONTEND_TASK_ARN \
      --region $REGION \
      --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' \
      --output text 2>/dev/null || echo "")
    
    if [ -n "$ENI_ID" ] && [ "$ENI_ID" != "None" ]; then
      FRONTEND_IP=$(aws ec2 describe-network-interfaces \
        --network-interface-ids $ENI_ID \
        --region $REGION \
        --query 'NetworkInterfaces[0].Association.PublicIp' \
        --output text 2>/dev/null || echo "")
      
      if [ -n "$FRONTEND_IP" ] && [ "$FRONTEND_IP" != "None" ]; then
        FRONTEND_ORIGIN="http://${FRONTEND_IP}:3000"
        if echo "$CURRENT_CORS" | grep -q "$FRONTEND_IP"; then
          echo "   ✅ CORS includes current frontend IP: $FRONTEND_IP"
        else
          echo "   ❌ CORS does NOT include current frontend IP: $FRONTEND_IP"
          echo "   🔧 FIX: Run ./sync-api-cors.sh"
        fi
      fi
    fi
  fi
else
  echo "   ❌ CORS not configured!"
fi

# 6. Check Frontend API URL
echo ""
echo "6️⃣  Checking Frontend API URL Configuration..."
FRONTEND_API_URL=$(aws ecs describe-task-definition \
  --task-definition esa-iagen-frontend \
  --region $REGION \
  --query 'taskDefinition.containerDefinitions[0].environment[?name==`NEXT_PUBLIC_API_URL`].value' \
  --output text 2>/dev/null || echo "")

if [ -n "$FRONTEND_API_URL" ]; then
  if echo "$FRONTEND_API_URL" | grep -q "alb.*elb.amazonaws.com"; then
    echo "   ✅ Frontend using ALB URL: $FRONTEND_API_URL"
    if [ "$FRONTEND_API_URL" = "http://$ALB_DNS_NAME" ]; then
      echo "      ✅ ALB URL matches current ALB DNS"
    else
      echo "      ⚠️  ALB URL doesn't match current ALB DNS"
      echo "      Expected: http://$ALB_DNS_NAME"
      echo "      🔧 FIX: Run ./register-task-definitions.sh"
    fi
  elif echo "$FRONTEND_API_URL" | grep -q "localhost"; then
    echo "   ❌ Frontend still using localhost: $FRONTEND_API_URL"
    echo "   🔧 FIX: Frontend image needs to be rebuilt with ALB URL"
  else
    echo "   ⚠️  Frontend using: $FRONTEND_API_URL"
  fi
else
  echo "   ❌ Frontend API URL not configured!"
fi

# 7. Test ALB Connectivity
echo ""
echo "7️⃣  Testing ALB Connectivity..."
echo "   Testing: http://$ALB_DNS_NAME/health"

HEALTH_RESPONSE=$(curl -s -w "\n%{http_code}" --max-time 10 \
  "http://$ALB_DNS_NAME/health" 2>/dev/null || echo -e "\n000")

HTTP_CODE=$(echo "$HEALTH_RESPONSE" | tail -1)
RESPONSE_BODY=$(echo "$HEALTH_RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "200" ]; then
  echo "      ✅ ALB is reachable (HTTP $HTTP_CODE)"
  echo "      Response: $(echo $RESPONSE_BODY | head -c 100)..."
else
  echo "      ❌ ALB not reachable (HTTP $HTTP_CODE)"
  echo "      This could indicate:"
  echo "         - Security group blocking traffic"
  echo "         - ALB not active"
  echo "         - No healthy targets"
fi

# 8. Test ALB with CORS headers
echo ""
echo "8️⃣  Testing ALB with CORS (simulating frontend request)..."
FRONTEND_ORIGIN="http://13.53.200.78:3000"
CORS_TEST=$(curl -s -w "\n%{http_code}" -H "Origin: $FRONTEND_ORIGIN" \
  --max-time 10 "http://$ALB_DNS_NAME/api/v1/chat/stream?query=test" 2>/dev/null || echo -e "\n000")

CORS_HTTP_CODE=$(echo "$CORS_TEST" | tail -1)
if [ "$CORS_HTTP_CODE" = "200" ] || [ "$CORS_HTTP_CODE" = "000" ]; then
  # Check for CORS headers in verbose output
  CORS_HEADERS=$(curl -s -I -H "Origin: $FRONTEND_ORIGIN" \
    --max-time 10 "http://$ALB_DNS_NAME/health" 2>/dev/null | grep -i "access-control" || echo "")
  
  if [ -n "$CORS_HEADERS" ]; then
    echo "      ✅ CORS headers present"
    echo "$CORS_HEADERS" | sed 's/^/         /'
  else
    echo "      ⚠️  No CORS headers in response"
    echo "      (This might be OK if endpoint doesn't require CORS)"
  fi
fi

# 9. Check API Service Status
echo ""
echo "9️⃣  Checking API Service Status..."
API_SERVICE=$(aws ecs describe-services \
  --cluster $CLUSTER \
  --services esa-iagen-api-service \
  --region $REGION \
  --query 'services[0]' \
  --output json 2>/dev/null || echo "{}")

API_RUNNING=$(echo "$API_SERVICE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('runningCount', 0))
" 2>/dev/null || echo "0")

API_DESIRED=$(echo "$API_SERVICE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(data.get('desiredCount', 0))
" 2>/dev/null || echo "0")

if [ "$API_RUNNING" = "$API_DESIRED" ] && [ "$API_RUNNING" -gt 0 ]; then
  echo "   ✅ API service running: $API_RUNNING/$API_DESIRED tasks"
else
  echo "   ❌ API service not running: $API_RUNNING/$API_DESIRED tasks"
fi

# Check if API is registered with ALB
HAS_LOAD_BALANCER=$(echo "$API_SERVICE" | python3 -c "
import sys, json
data = json.load(sys.stdin)
lbs = data.get('loadBalancers', [])
print('true' if lbs else 'false')
" 2>/dev/null || echo "false")

if [ "$HAS_LOAD_BALANCER" = "true" ]; then
  echo "   ✅ API service registered with ALB"
else
  echo "   ❌ API service NOT registered with ALB"
  echo "   🔧 FIX: Recreate API service with ALB target group"
fi

# Summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 Diagnostic Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

ISSUES=0

if [ "$ALB_STATE" != "active" ]; then
  echo "❌ ALB is not active"
  ISSUES=$((ISSUES + 1))
fi

if [ "$HAS_PORT_80" != "true" ]; then
  echo "❌ ALB Security Group missing port 80 rule"
  ISSUES=$((ISSUES + 1))
fi

if [ "$HAS_ALB_TO_API" = "false" ]; then
  echo "❌ API Security Group missing ALB → API rule"
  ISSUES=$((ISSUES + 1))
fi

if [ "$HEALTHY_COUNT" -eq 0 ]; then
  echo "❌ No healthy targets in target group"
  ISSUES=$((ISSUES + 1))
fi

if [ "$API_RUNNING" -eq 0 ]; then
  echo "❌ API service not running"
  ISSUES=$((ISSUES + 1))
fi

if [ "$HAS_LOAD_BALANCER" != "true" ]; then
  echo "❌ API service not registered with ALB"
  ISSUES=$((ISSUES + 1))
fi

if [ "$ISSUES" -eq 0 ]; then
  echo "✅ All infrastructure checks passed!"
  echo ""
  echo "If frontend still can't connect, the issue might be:"
  echo "   1. Frontend image has localhost:8002 hardcoded (needs rebuild)"
  echo "   2. CORS not synced (run ./sync-api-cors.sh)"
  echo "   3. Browser cache (try hard refresh: Cmd+Shift+R)"
  echo ""
  echo "Next steps:"
  echo "   1. Check browser console for exact error"
  echo "   2. Check Network tab - what URL is frontend trying to use?"
  echo "   3. Verify frontend image was rebuilt with ALB URL"
else
  echo "❌ Found $ISSUES issue(s) that need to be fixed"
  echo ""
  echo "🔧 Quick Fixes:"
  echo ""
  
  if [ "$HAS_PORT_80" != "true" ]; then
    echo "# Fix ALB Security Group (allow port 80 from Internet):"
    echo "aws ec2 authorize-security-group-ingress \\"
    echo "  --group-id $ALB_SG \\"
    echo "  --protocol tcp \\"
    echo "  --port 80 \\"
    echo "  --cidr 0.0.0.0/0 \\"
    echo "  --region $REGION"
    echo ""
  fi
  
  if [ "$HAS_ALB_TO_API" = "false" ]; then
    echo "# Fix API Security Group (allow port 8000 from ALB):"
    echo "aws ec2 authorize-security-group-ingress \\"
    echo "  --group-id $SECURITY_GROUP_ID \\"
    echo "  --protocol tcp \\"
    echo "  --port 8000 \\"
    echo "  --source-group $ALB_SG \\"
    echo "  --region $REGION"
    echo ""
  fi
  
  if [ "$HEALTHY_COUNT" -eq 0 ]; then
    echo "# Check why targets are unhealthy:"
    echo "aws logs tail /ecs/esa-iagen --filter-pattern 'api' --since 10m --region $REGION"
    echo ""
  fi
fi

echo ""
echo "💡 For detailed logs:"
echo "   aws logs tail /ecs/esa-iagen --follow --region $REGION"

