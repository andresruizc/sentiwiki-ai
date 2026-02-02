#!/bin/bash
# Cleanup AWS Infrastructure
# This script removes all AWS resources created for ECS deployment
# Use with caution - this will delete everything!

set -e

# Disable AWS CLI pager to prevent hanging
export AWS_PAGER=""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}⚠️  WARNING: This script will delete ALL AWS infrastructure!${NC}"
echo ""
echo "This includes:"
echo "  - ECS Services (Qdrant, API, Frontend)"
echo "  - ECS Task Definitions"
echo "  - Service Discovery services and namespace"
echo "  - Security Group and rules"
echo "  - CloudWatch Log Group"
echo "  - ECS Cluster"
echo ""

# Load infrastructure IDs if available
if [ -f "../infrastructure-ids.txt" ]; then
  source ../infrastructure-ids.txt
  echo "📋 Loaded infrastructure IDs from infrastructure-ids.txt"
else
  echo -e "${YELLOW}⚠️  infrastructure-ids.txt not found. Using defaults...${NC}"
  AWS_REGION=${AWS_REGION:-"eu-north-1"}
  AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")
fi

echo ""
echo "Region: ${AWS_REGION:-"eu-north-1"}"
echo "Account ID: ${AWS_ACCOUNT_ID:-"unknown"}"
echo ""

# Confirmation
read -p "Are you sure you want to continue? (type 'yes' to confirm): " confirm
if [ "$confirm" != "yes" ]; then
  echo "❌ Cleanup cancelled."
  exit 0
fi

echo ""
echo "🧹 Starting cleanup..."
echo ""

# Set region
export AWS_REGION=${AWS_REGION:-"eu-north-1"}

# 1. Delete ECS Services
echo "📦 Deleting ECS services..."
SERVICES=(
  "esa-iagen-qdrant-service"
  "esa-iagen-api-service"
  "esa-iagen-frontend-service"
  "esa-iagen-prometheus-service"
  "esa-iagen-grafana-service"
)

for SERVICE in "${SERVICES[@]}"; do
  echo "  Deleting service: $SERVICE..."
  aws ecs update-service \
    --cluster esa-iagen-cluster \
    --service $SERVICE \
    --desired-count 0 \
    --region $AWS_REGION \
    2>/dev/null || echo "    Service $SERVICE not found or already stopped"
  
  aws ecs delete-service \
    --cluster esa-iagen-cluster \
    --service $SERVICE \
    --force \
    --region $AWS_REGION \
    2>/dev/null || echo "    Service $SERVICE not found or already deleted"
done

echo "⏳ Waiting for services to be deleted..."
sleep 10

echo "✅ ECS services deleted"

# 2. Delete Service Discovery Services
echo ""
echo "🔍 Deleting Service Discovery services..."

if [ -n "$NAMESPACE_ID" ]; then
  # List all services in the namespace
  SERVICE_IDS=$(aws servicediscovery list-services \
    --filters "Name=NAMESPACE_ID,Values=$NAMESPACE_ID" \
    --region $AWS_REGION \
    --query 'Services[*].Id' \
    --output text 2>/dev/null || echo "")
  
  if [ -n "$SERVICE_IDS" ]; then
    for SERVICE_ID in $SERVICE_IDS; do
      SERVICE_NAME=$(aws servicediscovery get-service \
        --id $SERVICE_ID \
        --region $AWS_REGION \
        --query 'Service.Name' \
        --output text 2>/dev/null || echo "unknown")
      echo "  Deleting service discovery: $SERVICE_NAME ($SERVICE_ID)..."
      aws servicediscovery delete-service \
        --id $SERVICE_ID \
        --region $AWS_REGION \
        2>/dev/null || echo "    Service $SERVICE_NAME not found"
    done
  else
    echo "  No service discovery services found"
  fi
else
  echo "  ⚠️  NAMESPACE_ID not found, skipping service discovery cleanup"
fi

echo "✅ Service Discovery services deleted"

# 3. Delete Service Discovery Namespace
echo ""
echo "🔍 Deleting Service Discovery namespace..."

if [ -n "$NAMESPACE_ID" ]; then
  echo "  Deleting namespace: $NAMESPACE_ID..."
  aws servicediscovery delete-namespace \
    --id $NAMESPACE_ID \
    --region $AWS_REGION \
    2>/dev/null || echo "    Namespace not found or already deleted"
else
  # Try to find it
  NAMESPACE_ID=$(aws servicediscovery list-namespaces \
    --filters "Name=Name,Values=esa-iagen.local" \
    --region $AWS_REGION \
    --query 'Namespaces[0].Id' \
    --output text 2>/dev/null || echo "")
  
  if [ -n "$NAMESPACE_ID" ] && [ "$NAMESPACE_ID" != "None" ]; then
    echo "  Found namespace: $NAMESPACE_ID, deleting..."
    aws servicediscovery delete-namespace \
      --id $NAMESPACE_ID \
      --region $AWS_REGION \
      2>/dev/null || echo "    Namespace not found or already deleted"
  else
    echo "  No namespace found"
  fi
fi

echo "✅ Service Discovery namespace deleted"

# 4. Delete ECS Task Definitions
echo ""
echo "📝 Deregistering ECS task definitions..."

TASK_DEFINITIONS=(
  "esa-iagen-qdrant"
  "esa-iagen-api"
  "esa-iagen-frontend"
  "esa-iagen-prometheus"
  "esa-iagen-grafana"
)

for TASK_DEF in "${TASK_DEFINITIONS[@]}"; do
  echo "  Deregistering task definition: $TASK_DEF..."
  # Get all revisions
  REVISIONS=$(aws ecs list-task-definitions \
    --family-prefix $TASK_DEF \
    --region $AWS_REGION \
    --query 'taskDefinitionArns[*]' \
    --output text 2>/dev/null || echo "")
  
  if [ -n "$REVISIONS" ]; then
    for REVISION in $REVISIONS; do
      aws ecs deregister-task-definition \
        --task-definition $REVISION \
        --region $AWS_REGION \
        2>/dev/null || echo "    Task definition $REVISION not found"
    done
  else
    echo "    No task definitions found for $TASK_DEF"
  fi
done

echo "✅ Task definitions deregistered"

# 5. Delete Security Group Rules and Security Group
echo ""
echo "🔒 Deleting Security Group..."

if [ -n "$SECURITY_GROUP_ID" ]; then
  echo "  Security Group ID: $SECURITY_GROUP_ID"
  
  # Delete all ingress rules
  echo "  Deleting ingress rules..."
  INGRESS_RULES=$(aws ec2 describe-security-groups \
    --group-ids $SECURITY_GROUP_ID \
    --region $AWS_REGION \
    --query 'SecurityGroups[0].IpPermissions[*]' \
    --output json 2>/dev/null || echo "[]")
  
  if [ "$INGRESS_RULES" != "[]" ] && [ -n "$INGRESS_RULES" ]; then
    aws ec2 revoke-security-group-ingress \
      --group-id $SECURITY_GROUP_ID \
      --ip-permissions "$INGRESS_RULES" \
      --region $AWS_REGION \
      2>/dev/null || echo "    Could not revoke ingress rules"
  fi
  
  # Delete all egress rules (except default)
  echo "  Deleting egress rules..."
  EGRESS_RULES=$(aws ec2 describe-security-groups \
    --group-ids $SECURITY_GROUP_ID \
    --region $AWS_REGION \
    --query 'SecurityGroups[0].IpPermissionsEgress[?FromPort!=`-1`]' \
    --output json 2>/dev/null || echo "[]")
  
  if [ "$EGRESS_RULES" != "[]" ] && [ -n "$EGRESS_RULES" ]; then
    aws ec2 revoke-security-group-egress \
      --group-id $SECURITY_GROUP_ID \
      --ip-permissions "$EGRESS_RULES" \
      --region $AWS_REGION \
      2>/dev/null || echo "    Could not revoke egress rules"
  fi
  
  # Delete security group
  echo "  Deleting security group..."
  aws ec2 delete-security-group \
    --group-id $SECURITY_GROUP_ID \
    --region $AWS_REGION \
    2>/dev/null || echo "    Security group not found or in use"
else
  # Try to find it
  if [ -n "$VPC_ID" ]; then
    SECURITY_GROUP_ID=$(aws ec2 describe-security-groups \
      --filters "Name=group-name,Values=esa-iagen-sg" "Name=vpc-id,Values=$VPC_ID" \
      --region $AWS_REGION \
      --query 'SecurityGroups[0].GroupId' \
      --output text 2>/dev/null || echo "")
    
    if [ -n "$SECURITY_GROUP_ID" ] && [ "$SECURITY_GROUP_ID" != "None" ]; then
      echo "  Found security group: $SECURITY_GROUP_ID, deleting..."
      aws ec2 delete-security-group \
        --group-id $SECURITY_GROUP_ID \
        --region $AWS_REGION \
        2>/dev/null || echo "    Security group in use or not found"
    else
      echo "  No security group found"
    fi
  else
    echo "  ⚠️  VPC_ID not found, skipping security group cleanup"
  fi
fi

echo "✅ Security Group deleted"

# 6. Delete CloudWatch Log Group
echo ""
echo "📊 Deleting CloudWatch Log Group..."

aws logs delete-log-group \
  --log-group-name /ecs/esa-iagen \
  --region $AWS_REGION \
  2>/dev/null || echo "  Log group not found or already deleted"

echo "✅ CloudWatch Log Group deleted"

# 7. Delete Application Load Balancer
echo ""
echo "⚖️  Deleting Application Load Balancer..."

if [ -n "$ALB_ARN" ] && [ "$ALB_ARN" != "None" ]; then
  echo "  Deleting ALB: $ALB_ARN"
  
  # Delete listeners first
  LISTENER_ARNS=$(aws elbv2 describe-listeners \
    --load-balancer-arn $ALB_ARN \
    --region $AWS_REGION \
    --query 'Listeners[*].ListenerArn' \
    --output text 2>/dev/null || echo "")
  
  if [ -n "$LISTENER_ARNS" ]; then
    for LISTENER_ARN in $LISTENER_ARNS; do
      echo "    Deleting listener: $LISTENER_ARN"
      aws elbv2 delete-listener \
        --listener-arn $LISTENER_ARN \
        --region $AWS_REGION \
        2>/dev/null || echo "      Listener not found"
    done
  fi
  
  # Delete target group
  if [ -n "$TARGET_GROUP_ARN" ] && [ "$TARGET_GROUP_ARN" != "None" ]; then
    echo "  Deleting target group: $TARGET_GROUP_ARN"
    aws elbv2 delete-target-group \
      --target-group-arn $TARGET_GROUP_ARN \
      --region $AWS_REGION \
      2>/dev/null || echo "    Target group not found or in use"
  else
    # Try to find it by name
    TARGET_GROUP_ARN=$(aws elbv2 describe-target-groups \
      --names esa-iagen-api-targets \
      --region $AWS_REGION \
      --query 'TargetGroups[0].TargetGroupArn' \
      --output text 2>/dev/null || echo "")
    
    if [ -n "$TARGET_GROUP_ARN" ] && [ "$TARGET_GROUP_ARN" != "None" ]; then
      echo "  Found target group: $TARGET_GROUP_ARN, deleting..."
      aws elbv2 delete-target-group \
        --target-group-arn $TARGET_GROUP_ARN \
        --region $AWS_REGION \
        2>/dev/null || echo "    Target group in use or not found"
    fi
  fi

  # Delete frontend target group
  if [ -n "$FRONTEND_TARGET_GROUP_ARN" ] && [ "$FRONTEND_TARGET_GROUP_ARN" != "None" ]; then
    echo "  Deleting frontend target group: $FRONTEND_TARGET_GROUP_ARN"
    aws elbv2 delete-target-group \
      --target-group-arn $FRONTEND_TARGET_GROUP_ARN \
      --region $AWS_REGION \
      2>/dev/null || echo "    Frontend target group not found or in use"
  else
    # Try to find it by name
    FRONTEND_TARGET_GROUP_ARN=$(aws elbv2 describe-target-groups \
      --names esa-iagen-frontend-targets \
      --region $AWS_REGION \
      --query 'TargetGroups[0].TargetGroupArn' \
      --output text 2>/dev/null || echo "")

    if [ -n "$FRONTEND_TARGET_GROUP_ARN" ] && [ "$FRONTEND_TARGET_GROUP_ARN" != "None" ]; then
      echo "  Found frontend target group: $FRONTEND_TARGET_GROUP_ARN, deleting..."
      aws elbv2 delete-target-group \
        --target-group-arn $FRONTEND_TARGET_GROUP_ARN \
        --region $AWS_REGION \
        2>/dev/null || echo "    Frontend target group in use or not found"
    fi
  fi

  # Delete ALB
  echo "  Deleting ALB..."
  aws elbv2 delete-load-balancer \
    --load-balancer-arn $ALB_ARN \
    --region $AWS_REGION \
    2>/dev/null || echo "    ALB not found or already deleted"
else
  # Try to find ALB by name
  ALB_ARN=$(aws elbv2 describe-load-balancers \
    --names esa-iagen-api-alb \
    --region $AWS_REGION \
    --query 'LoadBalancers[0].LoadBalancerArn' \
    --output text 2>/dev/null || echo "")
  
  if [ -n "$ALB_ARN" ] && [ "$ALB_ARN" != "None" ]; then
    echo "  Found ALB: $ALB_ARN, deleting..."
    
    # Delete listeners
    LISTENER_ARNS=$(aws elbv2 describe-listeners \
      --load-balancer-arn $ALB_ARN \
      --region $AWS_REGION \
      --query 'Listeners[*].ListenerArn' \
      --output text 2>/dev/null || echo "")
    
    for LISTENER_ARN in $LISTENER_ARNS; do
      aws elbv2 delete-listener \
        --listener-arn $LISTENER_ARN \
        --region $AWS_REGION \
        2>/dev/null || true
    done
    
    # Delete target groups
    TARGET_GROUP_ARNS=$(aws elbv2 describe-target-groups \
      --load-balancer-arn $ALB_ARN \
      --region $AWS_REGION \
      --query 'TargetGroups[*].TargetGroupArn' \
      --output text 2>/dev/null || echo "")
    
    for TG_ARN in $TARGET_GROUP_ARNS; do
      aws elbv2 delete-target-group \
        --target-group-arn $TG_ARN \
        --region $AWS_REGION \
        2>/dev/null || true
    done
    
    # Delete ALB
    aws elbv2 delete-load-balancer \
      --load-balancer-arn $ALB_ARN \
      --region $AWS_REGION \
      2>/dev/null || echo "    ALB not found or already deleted"
  else
    echo "  No ALB found"
  fi
fi

echo "✅ Application Load Balancer deleted"

# 8. Delete ECS Cluster
echo ""
echo "📦 Deleting ECS Cluster..."

aws ecs delete-cluster \
  --cluster esa-iagen-cluster \
  --region $AWS_REGION \
  --output text \
  2>/dev/null || echo "  Cluster not found or already deleted"

echo "✅ ECS Cluster deleted"

# 9. Clean task definition files (remove account IDs and sensitive values)
echo ""
echo "🧹 Cleaning task definition files..."

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLEAN_SCRIPT="$SCRIPT_DIR/clean-task-definitions.sh"

if [ -f "$CLEAN_SCRIPT" ]; then
  # Use account ID and region from infrastructure-ids.txt if available, or from AWS CLI
  if [ -n "$AWS_ACCOUNT_ID" ] && [ -n "$AWS_REGION" ]; then
    echo "  Cleaning task definitions with Account ID: $AWS_ACCOUNT_ID, Region: $AWS_REGION"
    "$CLEAN_SCRIPT" "$AWS_ACCOUNT_ID" "$AWS_REGION" || echo "  ⚠️  Could not clean task definitions (they may already be cleaned)"
  else
    # Try to get from AWS CLI
    DETECTED_ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")
    DETECTED_REGION=${AWS_REGION:-$(aws configure get region 2>/dev/null || echo "eu-north-1")}
    
    if [ -n "$DETECTED_ACCOUNT" ] && [ -n "$DETECTED_REGION" ]; then
      echo "  Cleaning task definitions with Account ID: $DETECTED_ACCOUNT, Region: $DETECTED_REGION"
      "$CLEAN_SCRIPT" "$DETECTED_ACCOUNT" "$DETECTED_REGION" || echo "  ⚠️  Could not clean task definitions (they may already be cleaned)"
    else
      echo "  ⚠️  Could not determine account ID or region, skipping task definition cleanup"
      echo "  You can run manually: $CLEAN_SCRIPT [ACCOUNT_ID] [REGION]"
    fi
  fi
else
  echo "  ⚠️  clean-task-definitions.sh not found, skipping task definition cleanup"
fi

echo "✅ Task definition files cleaned"

# 10. Clean up infrastructure-ids.txt
echo ""
echo "🧹 Cleaning up infrastructure-ids.txt..."

if [ -f "../infrastructure-ids.txt" ]; then
  rm -f ../infrastructure-ids.txt
  echo "✅ infrastructure-ids.txt deleted"
else
  echo "  infrastructure-ids.txt not found"
fi

# Summary
echo ""
echo -e "${GREEN}✅ Cleanup complete!${NC}"
echo ""
echo "Deleted resources:"
echo "  ✅ ECS Services"
echo "  ✅ ECS Task Definitions"
echo "  ✅ Service Discovery (services and namespace)"
echo "  ✅ Security Group"
echo "  ✅ CloudWatch Log Group"
echo "  ✅ Application Load Balancer (ALB)"
echo "  ✅ ECS Cluster"
echo "  ✅ Task definition files cleaned (account IDs removed)"
echo ""
echo -e "${YELLOW}Note: ECR repositories and images are NOT deleted.${NC}"
echo -e "${YELLOW}To delete ECR repositories, run:${NC}"
echo "  aws ecr delete-repository --repository-name esa-iagen-api --force --region $AWS_REGION"
echo "  aws ecr delete-repository --repository-name esa-iagen-frontend --force --region $AWS_REGION"
echo ""
echo -e "${YELLOW}Note: IAM roles are NOT deleted (may be used by other resources).${NC}"
echo -e "${YELLOW}To delete IAM role manually, run:${NC}"
echo "  aws iam detach-role-policy --role-name ecsTaskExecutionRole --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
echo "  aws iam delete-role --role-name ecsTaskExecutionRole"
echo ""
echo -e "${YELLOW}Note: Network resources are NOT deleted (persistent):${NC}"
echo "  - VPC (default VPC)"
echo "  - Subnets"
echo "  - Route Tables and associations (subnets remain public)"
echo "  - Internet Gateway"
echo ""
echo "  These are AWS account-level resources that persist across deployments."
echo "  The route table associations (making subnets public) will remain."

