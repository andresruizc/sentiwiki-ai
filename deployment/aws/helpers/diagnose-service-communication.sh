#!/bin/bash
# Diagnose service-to-service communication issues
# Checks Service Discovery, security groups, and service registration

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

echo "🔍 Diagnosing service-to-service communication..."
echo "   Region: $REGION"
echo "   VPC: $VPC_ID"
echo "   Security Group: $SECURITY_GROUP_ID"
echo ""

# 1. Check Service Discovery Namespace
echo "1️⃣  Checking Service Discovery Namespace..."
if [ -n "$NAMESPACE_ID" ] && [ "$NAMESPACE_ID" != "None" ]; then
  NAMESPACE_NAME=$(aws servicediscovery get-namespace \
    --id $NAMESPACE_ID \
    --region $REGION \
    --query 'Namespace.Name' \
    --output text 2>/dev/null || echo "")
  
  if [ -n "$NAMESPACE_NAME" ]; then
    echo "   ✅ Namespace exists: $NAMESPACE_ID ($NAMESPACE_NAME)"
  else
    echo "   ❌ Namespace not found: $NAMESPACE_ID"
  fi
else
  echo "   ❌ NAMESPACE_ID not set in infrastructure-ids.txt"
fi

# 2. Check Service Discovery Services
echo ""
echo "2️⃣  Checking Service Discovery Services..."
if [ -n "$NAMESPACE_ID" ] && [ "$NAMESPACE_ID" != "None" ]; then
  SERVICES=$(aws servicediscovery list-services \
    --filters "Name=NAMESPACE_ID,Values=$NAMESPACE_ID" \
    --region $REGION \
    --query 'Services[*].Name' \
    --output text 2>/dev/null || echo "")
  
  if [ -n "$SERVICES" ]; then
    echo "   ✅ Service Discovery services found:"
    for SERVICE in $SERVICES; do
      echo "      - $SERVICE"
    done
  else
    echo "   ❌ No Service Discovery services found in namespace"
    echo "      Run: ./create-services.sh"
  fi
else
  echo "   ⚠️  Cannot check (namespace ID missing)"
fi

# 3. Check ECS Service Registration
echo ""
echo "3️⃣  Checking ECS Service Registration with Service Discovery..."
for SERVICE_NAME in esa-iagen-qdrant-service esa-iagen-api-service; do
  echo "   Checking $SERVICE_NAME..."
  
  REGISTRY=$(aws ecs describe-services \
    --cluster $CLUSTER \
    --services $SERVICE_NAME \
    --region $REGION \
    --query 'services[0].serviceRegistries[0].registryArn' \
    --output text 2>/dev/null || echo "")
  
  if [ -n "$REGISTRY" ] && [ "$REGISTRY" != "None" ] && [ "$REGISTRY" != "null" ]; then
    echo "      ✅ Registered with Service Discovery"
  else
    echo "      ❌ NOT registered with Service Discovery"
    echo "         Service needs to be recreated with Service Discovery"
  fi
  
  # Check if service is running
  RUNNING=$(aws ecs describe-services \
    --cluster $CLUSTER \
    --services $SERVICE_NAME \
    --region $REGION \
    --query 'services[0].runningCount' \
    --output text 2>/dev/null || echo "0")
  
  DESIRED=$(aws ecs describe-services \
    --cluster $CLUSTER \
    --services $SERVICE_NAME \
    --region $REGION \
    --query 'services[0].desiredCount' \
    --output text 2>/dev/null || echo "0")
  
  if [ "$RUNNING" = "$DESIRED" ] && [ "$RUNNING" != "0" ]; then
    echo "      ✅ Service is running ($RUNNING/$DESIRED tasks)"
  else
    echo "      ⚠️  Service not running ($RUNNING/$DESIRED tasks)"
  fi
done

# 4. Check Security Group Rules
echo ""
echo "4️⃣  Checking Security Group Rules..."
SG_RULES=$(aws ec2 describe-security-groups \
  --group-ids $SECURITY_GROUP_ID \
  --region $REGION \
  --query 'SecurityGroups[0].IpPermissions' \
  --output json 2>/dev/null || echo "[]")

# Check if rule allows traffic from same security group
HAS_INTERNAL_RULE=$(echo "$SG_RULES" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for rule in data:
    if 'UserIdGroupPairs' in rule:
        for pair in rule['UserIdGroupPairs']:
            if pair.get('GroupId') == '$SECURITY_GROUP_ID':
                print('true')
                sys.exit(0)
print('false')
" 2>/dev/null || echo "false")

if [ "$HAS_INTERNAL_RULE" = "true" ]; then
  echo "   ✅ Security group allows internal traffic (service-to-service)"
else
  echo "   ❌ Security group does NOT allow internal traffic"
  echo ""
  echo "   🔧 FIX: Run this command:"
  echo "   aws ec2 authorize-security-group-ingress \\"
  echo "     --group-id $SECURITY_GROUP_ID \\"
  echo "     --protocol -1 \\"
  echo "     --source-group $SECURITY_GROUP_ID \\"
  echo "     --region $REGION"
fi

# 5. Check if services are in same VPC/security group
echo ""
echo "5️⃣  Checking Network Configuration..."
API_NETWORK=$(aws ecs describe-services \
  --cluster $CLUSTER \
  --services esa-iagen-api-service \
  --region $REGION \
  --query 'services[0].networkConfiguration.awsvpcConfiguration' \
  --output json 2>/dev/null || echo "{}")

QDRANT_NETWORK=$(aws ecs describe-services \
  --cluster $CLUSTER \
  --services esa-iagen-qdrant-service \
  --region $REGION \
  --query 'services[0].networkConfiguration.awsvpcConfiguration' \
  --output json 2>/dev/null || echo "{}")

API_SG=$(echo "$API_NETWORK" | python3 -c "import sys, json; data=json.load(sys.stdin); sgs=data.get('securityGroups', []); print(sgs[0] if sgs else '')" 2>/dev/null || echo "")
QDRANT_SG=$(echo "$QDRANT_NETWORK" | python3 -c "import sys, json; data=json.load(sys.stdin); sgs=data.get('securityGroups', []); print(sgs[0] if sgs else '')" 2>/dev/null || echo "")

if [ "$API_SG" = "$QDRANT_SG" ] && [ "$API_SG" = "$SECURITY_GROUP_ID" ]; then
  echo "   ✅ Both services use the same security group: $SECURITY_GROUP_ID"
else
  echo "   ❌ Services use different security groups:"
  echo "      API: $API_SG"
  echo "      Qdrant: $QDRANT_SG"
  echo "      Expected: $SECURITY_GROUP_ID"
fi

# 6. Check API task definition for Qdrant host
echo ""
echo "6️⃣  Checking API Task Definition Configuration..."
API_TASK_DEF=$(aws ecs describe-task-definition \
  --task-definition esa-iagen-api \
  --region $REGION \
  --query 'taskDefinition.containerDefinitions[0].environment' \
  --output json 2>/dev/null || echo "[]")

QDRANT_HOST=$(echo "$API_TASK_DEF" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for env in data:
    if env.get('name') == 'QDRANT__HOST':
        print(env.get('value', ''))
        break
" 2>/dev/null || echo "")

if [ "$QDRANT_HOST" = "qdrant.esa-iagen.local" ]; then
  echo "   ✅ API configured to use Service Discovery: $QDRANT_HOST"
else
  echo "   ❌ API not configured correctly:"
  echo "      QDRANT__HOST: $QDRANT_HOST"
  echo "      Expected: qdrant.esa-iagen.local"
fi

# Summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 Summary"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

ISSUES=0

if [ "$HAS_INTERNAL_RULE" != "true" ]; then
  echo "❌ Security group missing internal traffic rule"
  ISSUES=$((ISSUES + 1))
fi

if [ -z "$SERVICES" ] || [ "$SERVICES" = "None" ]; then
  echo "❌ Service Discovery services not found"
  ISSUES=$((ISSUES + 1))
fi

if [ "$QDRANT_HOST" != "qdrant.esa-iagen.local" ]; then
  echo "❌ API task definition not configured for Service Discovery"
  ISSUES=$((ISSUES + 1))
fi

if [ $ISSUES -eq 0 ]; then
  echo "✅ All checks passed! If communication still fails, check:"
  echo "   1. Service logs: aws logs tail /ecs/esa-iagen --follow --region $REGION"
  echo "   2. Qdrant is actually running and healthy"
  echo "   3. DNS resolution from API container"
else
  echo ""
  echo "🔧 Quick Fix Commands:"
  echo ""
  
  if [ "$HAS_INTERNAL_RULE" != "true" ]; then
    echo "# Fix security group:"
    echo "aws ec2 authorize-security-group-ingress \\"
    echo "  --group-id $SECURITY_GROUP_ID \\"
    echo "  --protocol -1 \\"
    echo "  --source-group $SECURITY_GROUP_ID \\"
    echo "  --region $REGION"
    echo ""
  fi
  
  if [ -z "$SERVICES" ] || [ "$SERVICES" = "None" ]; then
    echo "# Recreate services with Service Discovery:"
    echo "cd deployment/aws/scripts"
    echo "./create-services.sh"
    echo ""
  fi
fi

