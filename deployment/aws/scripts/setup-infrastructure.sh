#!/bin/bash
# Setup AWS Infrastructure for ECS Deployment
# This script creates all necessary AWS resources for Phase 4

set -e

# Disable AWS CLI pager to prevent hanging
export AWS_PAGER=""

# Load configuration
if [ -f "../infrastructure-ids.txt" ]; then
  echo "⚠️  infrastructure-ids.txt already exists. Infrastructure may already be set up."
  echo "   Delete it and re-run this script if you want to recreate everything."
  exit 1
fi

# Get region from environment or use default
AWS_REGION=${AWS_REGION:-"eu-north-1"}
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "🚀 Setting up AWS infrastructure for ECS deployment..."
echo "   Region: $AWS_REGION"
echo "   Account ID: $AWS_ACCOUNT_ID"
echo ""

# 1. Create ECS Cluster
echo "📦 Creating ECS cluster..."
aws ecs create-cluster \
  --cluster-name esa-iagen-cluster \
  --region $AWS_REGION \
  --query 'cluster.clusterName' \
  --output text || echo "Cluster may already exist"
echo "✅ ECS cluster created"

# 2. Create CloudWatch Log Group
echo "📊 Creating CloudWatch log group..."
aws logs create-log-group \
  --log-group-name /ecs/esa-iagen \
  --region $AWS_REGION \
  2>/dev/null || echo "Log group may already exist"
echo "✅ CloudWatch log group created"

# 3. Get default VPC and subnets
echo "🌐 Getting VPC and subnet information..."
VPC_ID=$(aws ec2 describe-vpcs \
  --filters "Name=isDefault,Values=true" \
  --query "Vpcs[0].VpcId" \
  --output text \
  --region $AWS_REGION)

if [ "$VPC_ID" == "None" ] || [ -z "$VPC_ID" ]; then
  echo "❌ No default VPC found. Please create a VPC first."
  exit 1
fi

# Get all subnets in the VPC
ALL_SUBNET_IDS=$(aws ec2 describe-subnets \
  --filters "Name=vpc-id,Values=$VPC_ID" \
  --query "Subnets[*].SubnetId" \
  --output text \
  --region $AWS_REGION)

# Filter for public subnets (subnets with MapPublicIpOnLaunch enabled)
# This is the most reliable way to identify public subnets
PUBLIC_SUBNET_IDS=""
for SUBNET_ID in $ALL_SUBNET_IDS; do
  MAP_PUBLIC_IP=$(aws ec2 describe-subnets \
    --subnet-ids $SUBNET_ID \
    --query "Subnets[0].MapPublicIpOnLaunch" \
    --output text \
    --region $AWS_REGION 2>/dev/null || echo "false")
  
  if [ "$MAP_PUBLIC_IP" = "true" ]; then
    PUBLIC_SUBNET_IDS="$PUBLIC_SUBNET_IDS $SUBNET_ID"
  fi
done

# Use public subnets if found, otherwise try to make them public automatically
if [ -n "$PUBLIC_SUBNET_IDS" ]; then
  SUBNET_IDS=$(echo $PUBLIC_SUBNET_IDS | xargs)
  echo "✅ Filtered to public subnets: $SUBNET_IDS"
else
  echo "⚠️  No public subnets found. Attempting to make subnets public automatically..."
  
  # Get Internet Gateway
  IGW_ID=$(aws ec2 describe-internet-gateways \
    --filters "Name=attachment.vpc-id,Values=$VPC_ID" \
    --query "InternetGateways[0].InternetGatewayId" \
    --output text \
    --region $AWS_REGION 2>/dev/null || echo "")
  
  if [ -z "$IGW_ID" ] || [ "$IGW_ID" = "None" ]; then
    SUBNET_IDS=$ALL_SUBNET_IDS
    echo "❌ No Internet Gateway found. Cannot make subnets public."
    echo "   Using all subnets, but tasks will fail to reach AWS services."
    echo "   Please create and attach an Internet Gateway to your VPC."
  else
    echo "   Found Internet Gateway: $IGW_ID"
    
    # Get or create public route table
    PUBLIC_RT_ID=$(aws ec2 describe-route-tables \
      --filters "Name=vpc-id,Values=$VPC_ID" "Name=route.gateway-id,Values=$IGW_ID" \
      --query "RouteTables[0].RouteTableId" \
      --output text \
      --region $AWS_REGION 2>/dev/null || echo "")
    
    if [ -z "$PUBLIC_RT_ID" ] || [ "$PUBLIC_RT_ID" = "None" ]; then
      echo "   Creating public route table..."
      PUBLIC_RT_ID=$(aws ec2 create-route-table \
        --vpc-id $VPC_ID \
        --region $AWS_REGION \
        --query 'RouteTable.RouteTableId' \
        --output text)
      
      aws ec2 create-route \
        --route-table-id $PUBLIC_RT_ID \
        --destination-cidr-block 0.0.0.0/0 \
        --gateway-id $IGW_ID \
        --region $AWS_REGION > /dev/null
      
      echo "   ✅ Created public route table with IGW route"
    else
      echo "   ✅ Found existing public route table: $PUBLIC_RT_ID"
    fi
    
    # Associate subnets with public route table
    MADE_PUBLIC=""
    for SUBNET_ID in $ALL_SUBNET_IDS; do
      CURRENT_RT=$(aws ec2 describe-route-tables \
        --filters "Name=association.subnet-id,Values=$SUBNET_ID" \
        --query "RouteTables[0].RouteTableId" \
        --output text \
        --region $AWS_REGION 2>/dev/null || echo "")
      
      if [ "$CURRENT_RT" != "$PUBLIC_RT_ID" ]; then
        echo "   Associating $SUBNET_ID with public route table..."
        aws ec2 associate-route-table \
          --subnet-id $SUBNET_ID \
          --route-table-id $PUBLIC_RT_ID \
          --region $AWS_REGION > /dev/null 2>&1 || true
        MADE_PUBLIC="$MADE_PUBLIC $SUBNET_ID"
      fi
    done
    
    if [ -n "$MADE_PUBLIC" ]; then
      echo "   ✅ Made subnets public: $MADE_PUBLIC"
    fi
    
    # Use all subnets (they're now public)
    SUBNET_IDS=$ALL_SUBNET_IDS
    echo "✅ All subnets are now public: $SUBNET_IDS"
  fi
fi

# Convert space-separated to comma-separated for infrastructure-ids.txt
SUBNET_IDS_COMMA=$(echo $SUBNET_IDS | tr ' ' ',')

SUBNET_COUNT=$(echo $SUBNET_IDS | wc -w)
if [ $SUBNET_COUNT -lt 2 ]; then
  echo "⚠️  Warning: Only $SUBNET_COUNT subnet(s) found. ECS Fargate needs at least 2 subnets for high availability."
fi

echo "✅ Found VPC: $VPC_ID"
echo "✅ Found $SUBNET_COUNT subnet(s): $SUBNET_IDS"

# 4. Create Security Group
echo "🔒 Creating security group..."
SECURITY_GROUP_ID=$(aws ec2 create-security-group \
  --group-name esa-iagen-sg \
  --description "Security group for ESA IAGEN ECS services" \
  --vpc-id $VPC_ID \
  --region $AWS_REGION \
  --query 'GroupId' \
  --output text 2>/dev/null || \
  aws ec2 describe-security-groups \
    --filters "Name=group-name,Values=esa-iagen-sg" "Name=vpc-id,Values=$VPC_ID" \
    --query 'SecurityGroups[0].GroupId' \
    --output text \
    --region $AWS_REGION)

echo "✅ Security group ID: $SECURITY_GROUP_ID"

# Add security group rules
echo "🔓 Configuring security group rules..."

# CRITICAL: Allow all outbound traffic (needed for ECS tasks to reach ECR, CloudWatch, Secrets Manager)
echo "   Adding outbound rule (allow all traffic)..."
aws ec2 authorize-security-group-egress \
  --group-id $SECURITY_GROUP_ID \
  --protocol -1 \
  --cidr 0.0.0.0/0 \
  --region $AWS_REGION \
  2>/dev/null || echo "   Outbound rule may already exist"

# NOTE: Ports 8000, 3000, 6333 are NOT exposed to the internet (0.0.0.0/0)
# These services are only accessible via:
#   - ALB (which forwards external traffic on port 80 to internal services)
#   - Internal service-to-service communication (via security group self-reference rule below)
# This is more secure than exposing all ports to the internet.
echo "   ℹ️  API (8000), Frontend (3000), Qdrant (6333) only accessible internally"
echo "   ℹ️  External access is via ALB on port 80"

# Optional: Prometheus and Grafana ports (uncomment if adding monitoring later)
# aws ec2 authorize-security-group-ingress \
#   --group-id $SECURITY_GROUP_ID \
#   --protocol tcp \
#   --port 9090 \
#   --cidr 0.0.0.0/0 \
#   --region $AWS_REGION \
#   2>/dev/null || echo "Rule may already exist"
#
# aws ec2 authorize-security-group-ingress \
#   --group-id $SECURITY_GROUP_ID \
#   --protocol tcp \
#   --port 3002 \
#   --cidr 0.0.0.0/0 \
#   --region $AWS_REGION \
#   2>/dev/null || echo "Rule may already exist"

# CRITICAL: Allow all traffic within security group (for service-to-service communication)
# This enables API ↔ Qdrant communication via Service Discovery
echo "   Adding internal traffic rule (service-to-service communication)..."
aws ec2 authorize-security-group-ingress \
  --group-id $SECURITY_GROUP_ID \
  --protocol -1 \
  --source-group $SECURITY_GROUP_ID \
  --region $AWS_REGION \
  2>/dev/null || echo "   Internal traffic rule may already exist"

echo "✅ Security group rules configured"

# 5. Create Service Discovery Namespace
echo "🔍 Creating service discovery namespace..."

# Check if namespace already exists
echo "   Checking for existing namespace..."
echo "   💡 Tip: If namespace exists, set EXISTING_NAMESPACE_ID=ns-xxxxx before running this script"

# Allow manual override via environment variable (e.g., EXISTING_NAMESPACE_ID=ns-oosaisk7cjtzked2)
if [ -n "$EXISTING_NAMESPACE_ID" ]; then
  echo "   Using provided namespace ID: $EXISTING_NAMESPACE_ID"
  # Verify it exists
  VERIFY_NAME=$(aws servicediscovery get-namespace \
    --id "$EXISTING_NAMESPACE_ID" \
    --region $AWS_REGION \
    --query 'Namespace.Name' \
    --output text 2>/dev/null || echo "")
  if [ -z "$VERIFY_NAME" ]; then
    echo "   ⚠️  Warning: Namespace ID $EXISTING_NAMESPACE_ID not found, will try to detect..."
    EXISTING_NAMESPACE_ID=""
  else
    echo "   ✅ Verified namespace exists: $VERIFY_NAME"
  fi
fi

if [ -z "$EXISTING_NAMESPACE_ID" ] || [ "$EXISTING_NAMESPACE_ID" = "None" ] || [ "$EXISTING_NAMESPACE_ID" = "null" ]; then
  # Method 1: Filter by name (use NAME in uppercase)
  EXISTING_NAMESPACE_ID=$(aws servicediscovery list-namespaces \
    --filters "Name=NAME,Values=esa-iagen.local" \
    --region $AWS_REGION \
    --query 'Namespaces[0].Id' \
    --output text 2>/dev/null || echo "")
  
  # Method 2: List all namespaces and find by name (more reliable)
  if [ -z "$EXISTING_NAMESPACE_ID" ] || [ "$EXISTING_NAMESPACE_ID" = "None" ] || [ "$EXISTING_NAMESPACE_ID" = "null" ]; then
    # Get all namespaces and search for the one with matching name
    ALL_NAMESPACES_JSON=$(aws servicediscovery list-namespaces \
      --region $AWS_REGION \
      --output json 2>/dev/null || echo "{\"Namespaces\":[]}")
    
    # Use jq if available, otherwise python
    if command -v jq &> /dev/null; then
      EXISTING_NAMESPACE_ID=$(echo "$ALL_NAMESPACES_JSON" | \
        jq -r '.Namespaces[] | select(.Name=="esa-iagen.local") | .Id' 2>/dev/null | head -1 || echo "")
    elif command -v python3 &> /dev/null; then
      EXISTING_NAMESPACE_ID=$(echo "$ALL_NAMESPACES_JSON" | \
        python3 -c "import sys, json; data=json.load(sys.stdin); \
        ns=[n for n in data.get('Namespaces', []) if n.get('Name')=='esa-iagen.local']; \
        print(ns[0]['Id'] if ns else '')" 2>/dev/null || echo "")
    fi
  fi
fi

if [ -n "$EXISTING_NAMESPACE_ID" ] && [ "$EXISTING_NAMESPACE_ID" != "None" ] && [ "$EXISTING_NAMESPACE_ID" != "null" ]; then
  echo "✅ Namespace already exists: $EXISTING_NAMESPACE_ID"
  NAMESPACE_ID=$EXISTING_NAMESPACE_ID
  NAMESPACE_ARN=$(aws servicediscovery get-namespace \
    --id $EXISTING_NAMESPACE_ID \
    --region $AWS_REGION \
    --query 'Namespace.Arn' \
    --output text 2>/dev/null || echo "")
  
  # Fallback: get from list if get-namespace fails (avoid filters - they're unreliable)
  if [ -z "$NAMESPACE_ARN" ] || [ "$NAMESPACE_ARN" = "None" ]; then
    ALL_NAMESPACES_JSON=$(aws servicediscovery list-namespaces \
      --region $AWS_REGION \
      --output json 2>/dev/null || echo "{\"Namespaces\":[]}")
    
    if command -v jq &> /dev/null; then
      NAMESPACE_ARN=$(echo "$ALL_NAMESPACES_JSON" | \
        jq -r '.Namespaces[] | select(.Name=="esa-iagen.local") | .Arn' 2>/dev/null | head -1 || echo "")
    elif command -v python3 &> /dev/null; then
      NAMESPACE_ARN=$(echo "$ALL_NAMESPACES_JSON" | \
        python3 -c "import sys, json; data=json.load(sys.stdin); \
        ns=[n for n in data.get('Namespaces', []) if n.get('Name')=='esa-iagen.local']; \
        print(ns[0]['Arn'] if ns else '')" 2>/dev/null || echo "")
    fi
  fi
  echo "✅ Using existing namespace: $NAMESPACE_ID"
else
  echo "📝 Creating new namespace..."
  OPERATION_ID=$(aws servicediscovery create-private-dns-namespace \
    --name esa-iagen.local \
    --vpc $VPC_ID \
    --region $AWS_REGION \
    --query 'OperationId' \
    --output text 2>/dev/null || echo "")
  
  if [ -n "$OPERATION_ID" ] && [ "$OPERATION_ID" != "None" ]; then
    echo "⏳ Waiting for namespace to be created (operation: $OPERATION_ID)..."
    
    # Poll operation status (max 90 seconds)
    MAX_ATTEMPTS=18
    ATTEMPT=0
    OPERATION_STATUS=""
    
    while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
      OPERATION_STATUS=$(aws servicediscovery get-operation \
        --operation-id $OPERATION_ID \
        --region $AWS_REGION \
        --query 'Operation.Status' \
        --output text 2>/dev/null || echo "UNKNOWN")
      
      if [ "$OPERATION_STATUS" = "SUCCESS" ]; then
        echo "✅ Namespace creation operation completed successfully"
        break
      elif [ "$OPERATION_STATUS" = "FAIL" ] || [ "$OPERATION_STATUS" = "FAILED" ]; then
        # Get error details
        ERROR_MESSAGE=$(aws servicediscovery get-operation \
          --operation-id $OPERATION_ID \
          --region $AWS_REGION \
          --query 'Operation.ErrorMessage' \
          --output text 2>/dev/null || echo "Unknown error")
        echo "⚠️  Operation failed: $ERROR_MESSAGE"
        echo "   Checking if namespace exists anyway..."
        break
      elif [ "$OPERATION_STATUS" = "UNKNOWN" ]; then
        echo "   ⚠️  Could not get operation status, will check namespace directly..."
        break
      else
        echo "   Status: $OPERATION_STATUS (attempt $((ATTEMPT + 1))/$MAX_ATTEMPTS)..."
      fi
      
      ATTEMPT=$((ATTEMPT + 1))
      sleep 5
    done
    
    # Check if we timed out while still pending
    if [ "$OPERATION_STATUS" = "PENDING" ] || [ "$ATTEMPT" -ge "$MAX_ATTEMPTS" ]; then
      if [ "$OPERATION_STATUS" = "PENDING" ]; then
        echo "   ⚠️  Operation still PENDING after $MAX_ATTEMPTS attempts (90 seconds)"
        echo "   This is normal - namespace creation can take a few minutes."
        echo "   Will check if namespace exists anyway..."
      fi
    fi
    
    # Get namespace ID after creation (try multiple times with increasing delays)
    echo "   Checking for namespace..."
    # Use method that doesn't rely on filters (more reliable)
    for i in 1 2 3 4 5; do
      sleep $((i * 2))  # 2s, 4s, 6s, 8s, 10s
      
      # Try to get namespace ID from operation result first
      if [ -z "$NAMESPACE_ID" ] || [ "$NAMESPACE_ID" = "None" ] || [ "$NAMESPACE_ID" = "null" ]; then
        # Get namespace ID from operation (if available)
        NAMESPACE_ID=$(aws servicediscovery get-operation \
          --operation-id $OPERATION_ID \
          --region $AWS_REGION \
          --query 'Operation.Targets.NAMESPACE' \
          --output text 2>/dev/null || echo "")
      fi
      
      # If still not found, list all namespaces and search (avoid filters - they're unreliable)
      if [ -z "$NAMESPACE_ID" ] || [ "$NAMESPACE_ID" = "None" ] || [ "$NAMESPACE_ID" = "null" ]; then
        ALL_NAMESPACES_JSON=$(aws servicediscovery list-namespaces \
          --region $AWS_REGION \
          --output json 2>/dev/null || echo "{\"Namespaces\":[]}")
        
        # Use jq if available, otherwise python
        if command -v jq &> /dev/null; then
          NAMESPACE_ID=$(echo "$ALL_NAMESPACES_JSON" | \
            jq -r '.Namespaces[] | select(.Name=="esa-iagen.local") | .Id' 2>/dev/null | head -1 || echo "")
        elif command -v python3 &> /dev/null; then
          NAMESPACE_ID=$(echo "$ALL_NAMESPACES_JSON" | \
            python3 -c "import sys, json; data=json.load(sys.stdin); \
            ns=[n for n in data.get('Namespaces', []) if n.get('Name')=='esa-iagen.local']; \
            print(ns[0]['Id'] if ns else '')" 2>/dev/null || echo "")
        fi
      fi
      
      if [ -n "$NAMESPACE_ID" ] && [ "$NAMESPACE_ID" != "None" ] && [ "$NAMESPACE_ID" != "null" ]; then
        echo "   ✅ Found namespace: $NAMESPACE_ID"
        break
      else
        echo "   ⏳ Still waiting for namespace to appear (attempt $i/5)..."
      fi
    done
    
    if [ -z "$NAMESPACE_ID" ] || [ "$NAMESPACE_ID" = "None" ] || [ "$NAMESPACE_ID" = "null" ]; then
      echo "❌ Failed to create namespace."
      echo "   Operation ID: $OPERATION_ID"
      echo "   Operation Status: $OPERATION_STATUS"
      echo ""
      echo "   Please check AWS Console or try running:"
      echo "   aws servicediscovery get-operation --operation-id $OPERATION_ID --region $AWS_REGION"
      echo ""
      echo "   You can also check if namespace exists:"
      echo "   aws servicediscovery list-namespaces --region $AWS_REGION | grep esa-iagen.local"
      exit 1
    fi
    
    # Get namespace ARN (use get-namespace if we have ID, otherwise list all)
    if [ -n "$NAMESPACE_ID" ] && [ "$NAMESPACE_ID" != "None" ] && [ "$NAMESPACE_ID" != "null" ]; then
      NAMESPACE_ARN=$(aws servicediscovery get-namespace \
        --id $NAMESPACE_ID \
        --region $AWS_REGION \
        --query 'Namespace.Arn' \
        --output text 2>/dev/null || echo "")
    fi
    
    # Fallback: list all and find by name
    if [ -z "$NAMESPACE_ARN" ] || [ "$NAMESPACE_ARN" = "None" ]; then
      ALL_NAMESPACES_JSON=$(aws servicediscovery list-namespaces \
        --region $AWS_REGION \
        --output json 2>/dev/null || echo "{\"Namespaces\":[]}")
      
      if command -v jq &> /dev/null; then
        NAMESPACE_ARN=$(echo "$ALL_NAMESPACES_JSON" | \
          jq -r '.Namespaces[] | select(.Name=="esa-iagen.local") | .Arn' 2>/dev/null | head -1 || echo "")
      elif command -v python3 &> /dev/null; then
        NAMESPACE_ARN=$(echo "$ALL_NAMESPACES_JSON" | \
          python3 -c "import sys, json; data=json.load(sys.stdin); \
          ns=[n for n in data.get('Namespaces', []) if n.get('Name')=='esa-iagen.local']; \
          print(ns[0]['Arn'] if ns else '')" 2>/dev/null || echo "")
      fi
    fi
    
    echo "✅ Service discovery namespace created: $NAMESPACE_ID"
  else
    echo "❌ Failed to create namespace. Operation ID not returned."
    exit 1
  fi
fi

# 8. Verify IAM role exists (already created manually)
echo "👤 Verifying IAM role for ECS tasks..."
ROLE_NAME="ecsTaskExecutionRole"

# Try to verify role exists (may fail due to permissions, which is OK)
if aws iam get-role --role-name $ROLE_NAME &>/dev/null; then
  echo "✅ IAM role '$ROLE_NAME' verified"
else
  echo "⚠️  Cannot verify IAM role (insufficient permissions)"
  echo "   Assuming role '$ROLE_NAME' exists (created manually)"
  echo "   Make sure the role name is exactly: $ROLE_NAME"
fi

# 9. Create Application Load Balancer (ALB) for API
echo ""
echo "⚖️  Creating Application Load Balancer for API..."

# Check if ALB already exists
EXISTING_ALB_ARN=$(aws elbv2 describe-load-balancers \
  --names esa-iagen-api-alb \
  --region $AWS_REGION \
  --query 'LoadBalancers[0].LoadBalancerArn' \
  --output text 2>/dev/null || echo "")

if [ -n "$EXISTING_ALB_ARN" ] && [ "$EXISTING_ALB_ARN" != "None" ]; then
  echo "✅ ALB already exists: $EXISTING_ALB_ARN"
  ALB_ARN=$EXISTING_ALB_ARN
  ALB_DNS_NAME=$(aws elbv2 describe-load-balancers \
    --load-balancer-arns $ALB_ARN \
    --region $AWS_REGION \
    --query 'LoadBalancers[0].DNSName' \
    --output text)
else
  echo "📝 Creating new ALB..."
  
  # Convert subnet IDs to array format (ALB needs at least 2 subnets in different AZs)
  SUBNET_ARRAY_ALB=$(echo $SUBNET_IDS | tr ' ' '\n' | head -2 | tr '\n' ' ' | xargs)
  SUBNET_COUNT_ALB=$(echo $SUBNET_ARRAY_ALB | wc -w)
  
  if [ $SUBNET_COUNT_ALB -lt 2 ]; then
    echo "⚠️  Warning: ALB requires at least 2 subnets in different AZs"
    echo "   Using all available subnets: $SUBNET_IDS"
    SUBNET_ARRAY_ALB=$SUBNET_IDS
  fi
  
  # Create ALB (internet-facing, HTTP only for cost savings)
  ALB_ARN=$(aws elbv2 create-load-balancer \
    --name esa-iagen-api-alb \
    --subnets $(echo $SUBNET_ARRAY_ALB | tr ' ' ' ') \
    --security-groups $SECURITY_GROUP_ID \
    --scheme internet-facing \
    --type application \
    --ip-address-type ipv4 \
    --region $AWS_REGION \
    --query 'LoadBalancers[0].LoadBalancerArn' \
    --output text 2>/dev/null || echo "")
  
  if [ -z "$ALB_ARN" ] || [ "$ALB_ARN" = "None" ]; then
    echo "❌ Failed to create ALB"
    exit 1
  fi
  
  echo "⏳ Waiting for ALB to be active..."
  aws elbv2 wait load-balancer-available \
    --load-balancer-arns $ALB_ARN \
    --region $AWS_REGION 2>/dev/null || echo "   ALB creation in progress..."
  
  ALB_DNS_NAME=$(aws elbv2 describe-load-balancers \
    --load-balancer-arns $ALB_ARN \
    --region $AWS_REGION \
    --query 'LoadBalancers[0].DNSName' \
    --output text)
  
  echo "✅ ALB created: $ALB_DNS_NAME"
fi

# 10. Create Target Group for API
echo ""
echo "🎯 Creating target group for API..."

# Check if target group already exists
EXISTING_TG_ARN=$(aws elbv2 describe-target-groups \
  --names esa-iagen-api-targets \
  --region $AWS_REGION \
  --query 'TargetGroups[0].TargetGroupArn' \
  --output text 2>/dev/null || echo "")

if [ -n "$EXISTING_TG_ARN" ] && [ "$EXISTING_TG_ARN" != "None" ]; then
  echo "✅ Target group already exists: $EXISTING_TG_ARN"
  TARGET_GROUP_ARN=$EXISTING_TG_ARN
else
  echo "📝 Creating new target group..."
  
  TARGET_GROUP_ARN=$(aws elbv2 create-target-group \
    --name esa-iagen-api-targets \
    --protocol HTTP \
    --port 8000 \
    --vpc-id $VPC_ID \
    --target-type ip \
    --health-check-path /health \
    --health-check-protocol HTTP \
    --health-check-interval-seconds 30 \
    --health-check-timeout-seconds 5 \
    --healthy-threshold-count 2 \
    --unhealthy-threshold-count 3 \
    --region $AWS_REGION \
    --query 'TargetGroups[0].TargetGroupArn' \
    --output text 2>/dev/null || echo "")
  
  if [ -z "$TARGET_GROUP_ARN" ] || [ "$TARGET_GROUP_ARN" = "None" ]; then
    echo "❌ Failed to create target group"
    exit 1
  fi
  
  echo "✅ Target group created: $TARGET_GROUP_ARN"
fi

# 10b. Create Target Group for Frontend
echo ""
echo "🎯 Creating target group for Frontend..."

EXISTING_FRONTEND_TG=$(aws elbv2 describe-target-groups \
  --names esa-iagen-frontend-targets \
  --region $AWS_REGION \
  --query 'TargetGroups[0].TargetGroupArn' \
  --output text 2>/dev/null || echo "")

if [ -n "$EXISTING_FRONTEND_TG" ] && [ "$EXISTING_FRONTEND_TG" != "None" ]; then
  echo "✅ Frontend target group already exists: $EXISTING_FRONTEND_TG"
  FRONTEND_TARGET_GROUP_ARN=$EXISTING_FRONTEND_TG
else
  echo "📝 Creating new frontend target group..."

  FRONTEND_TARGET_GROUP_ARN=$(aws elbv2 create-target-group \
    --name esa-iagen-frontend-targets \
    --protocol HTTP \
    --port 3000 \
    --vpc-id $VPC_ID \
    --target-type ip \
    --health-check-path / \
    --health-check-protocol HTTP \
    --health-check-interval-seconds 30 \
    --health-check-timeout-seconds 5 \
    --healthy-threshold-count 2 \
    --unhealthy-threshold-count 3 \
    --region $AWS_REGION \
    --query 'TargetGroups[0].TargetGroupArn' \
    --output text 2>/dev/null || echo "")

  if [ -z "$FRONTEND_TARGET_GROUP_ARN" ] || [ "$FRONTEND_TARGET_GROUP_ARN" = "None" ]; then
    echo "❌ Failed to create frontend target group"
    exit 1
  fi

  echo "✅ Frontend target group created: $FRONTEND_TARGET_GROUP_ARN"
fi

# 11. Create Listener on ALB (HTTP port 80) with path-based routing
echo ""
echo "🔊 Creating ALB listener with path-based routing..."
echo "   / → Frontend (default)"
echo "   /health, /docs, /redoc, /openapi.json, /metrics → API"
echo "   /api/* → API"

# Check if listener already exists
EXISTING_LISTENER_ARN=$(aws elbv2 describe-listeners \
  --load-balancer-arn $ALB_ARN \
  --region $AWS_REGION \
  --query 'Listeners[?Port==`80`].ListenerArn' \
  --output text 2>/dev/null || echo "")

if [ -n "$EXISTING_LISTENER_ARN" ] && [ "$EXISTING_LISTENER_ARN" != "None" ]; then
  echo "✅ Listener already exists: $EXISTING_LISTENER_ARN"
  LISTENER_ARN=$EXISTING_LISTENER_ARN

  # Update default action to Frontend
  echo "   Updating default action to Frontend..."
  aws elbv2 modify-listener \
    --listener-arn $LISTENER_ARN \
    --default-actions "Type=forward,TargetGroupArn=$FRONTEND_TARGET_GROUP_ARN" \
    --region $AWS_REGION \
    --output text > /dev/null 2>&1 || echo "   Could not update default action"
else
  echo "📝 Creating new listener (default → Frontend)..."

  LISTENER_ARN=$(aws elbv2 create-listener \
    --load-balancer-arn $ALB_ARN \
    --protocol HTTP \
    --port 80 \
    --default-actions "Type=forward,TargetGroupArn=$FRONTEND_TARGET_GROUP_ARN" \
    --region $AWS_REGION \
    --query 'Listeners[0].ListenerArn' \
    --output text 2>/dev/null || echo "")

  if [ -z "$LISTENER_ARN" ] || [ "$LISTENER_ARN" = "None" ]; then
    echo "❌ Failed to create listener"
    exit 1
  fi

  echo "✅ Listener created: $LISTENER_ARN"
fi

# 11b. Add path-based rules for API endpoints
echo ""
echo "📝 Adding path-based rules for API endpoints..."

# Function to add a rule if it doesn't exist
add_api_rule() {
  local path=$1
  local priority=$2
  
  EXISTING_RULE=$(aws elbv2 describe-rules \
    --listener-arn $LISTENER_ARN \
    --region $AWS_REGION \
    --query "Rules[?Conditions[0].PathPatternConfig.Values[0]=='$path'].RuleArn" \
    --output text 2>/dev/null || echo "")
  
  if [ -n "$EXISTING_RULE" ] && [ "$EXISTING_RULE" != "None" ]; then
    echo "   ✅ Rule for $path already exists"
    return 0
  fi
  
  aws elbv2 create-rule \
    --listener-arn $LISTENER_ARN \
    --priority $priority \
    --conditions "Field=path-pattern,PathPatternConfig={Values=['$path']}" \
    --actions "Type=forward,TargetGroupArn=$TARGET_GROUP_ARN" \
    --region $AWS_REGION \
    --output text > /dev/null 2>&1
  
  if [ $? -eq 0 ]; then
    echo "   ✅ Added rule: $path → API"
    return 0
  else
    echo "   ⚠️  Could not add rule for $path"
    return 1
  fi
}

# Add rules for FastAPI root-level endpoints (higher priority = lower number)
# These must come before the /api/* wildcard rule
echo "   Adding FastAPI documentation and health endpoints..."
add_api_rule "/health" 50
add_api_rule "/docs" 60
add_api_rule "/redoc" 61
add_api_rule "/openapi.json" 62
add_api_rule "/metrics" 63

# Add rule for /api/* → API (lower priority, catches all /api/* paths)
echo "   Adding API wildcard rule..."
API_RULE_EXISTS=$(aws elbv2 describe-rules \
  --listener-arn $LISTENER_ARN \
  --region $AWS_REGION \
  --query "Rules[?Conditions[0].PathPatternConfig.Values[0]=='/api/*'].RuleArn" \
  --output text 2>/dev/null || echo "")

if [ -n "$API_RULE_EXISTS" ] && [ "$API_RULE_EXISTS" != "None" ]; then
  echo "   ✅ API path rule already exists"
else
  aws elbv2 create-rule \
    --listener-arn $LISTENER_ARN \
    --priority 100 \
    --conditions "Field=path-pattern,PathPatternConfig={Values=['/api/*']}" \
    --actions "Type=forward,TargetGroupArn=$TARGET_GROUP_ARN" \
    --region $AWS_REGION \
    --output text > /dev/null 2>&1

  if [ $? -eq 0 ]; then
    echo "   ✅ Added rule: /api/* → API"
  else
    echo "   ⚠️  Could not add API rule (may already exist)"
  fi
fi

echo "✅ API routing rules configured"
echo "   - /health → API (health checks)"
echo "   - /docs → API (Swagger UI)"
echo "   - /redoc → API (ReDoc)"
echo "   - /openapi.json → API (OpenAPI schema)"
echo "   - /metrics → API (Prometheus metrics)"
echo "   - /api/* → API (all API endpoints)"

# Add security group rule for ALB (port 80)
echo ""
echo "🔓 Adding security group rule for ALB (port 80)..."
aws ec2 authorize-security-group-ingress \
  --group-id $SECURITY_GROUP_ID \
  --protocol tcp \
  --port 80 \
  --cidr 0.0.0.0/0 \
  --region $AWS_REGION \
  2>/dev/null || echo "   Rule may already exist"

echo "✅ Security group rule added"

# 12. Setup S3 Buckets
echo ""
echo "🪣 Setting up S3 buckets..."

S3_BUCKET_NAME="esa-iagen-data"
S3_CLOUDWATCH_BUCKET="esa-iagen-cloudwatch"

# Create main data bucket
echo "📦 Creating main data bucket: $S3_BUCKET_NAME"
aws s3api create-bucket \
  --bucket "$S3_BUCKET_NAME" \
  --region "$AWS_REGION" \
  --create-bucket-configuration LocationConstraint="$AWS_REGION" \
  2>/dev/null || echo "   Bucket may already exist"

# Enable versioning
echo "   Enabling versioning..."
aws s3api put-bucket-versioning \
  --bucket "$S3_BUCKET_NAME" \
  --versioning-configuration Status=Enabled \
  --region "$AWS_REGION" 2>/dev/null || true

# Enable encryption
echo "   Enabling encryption..."
aws s3api put-bucket-encryption \
  --bucket "$S3_BUCKET_NAME" \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }' \
  --region "$AWS_REGION" 2>/dev/null || true

# Block public access
echo "   Blocking public access..."
aws s3api put-public-access-block \
  --bucket "$S3_BUCKET_NAME" \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" \
  --region "$AWS_REGION" 2>/dev/null || true

# Create lifecycle policy (transition to cheaper storage over time)
echo "   Creating lifecycle policy..."
cat > /tmp/lifecycle-policy.json <<LIFECYCLE
{
  "Rules": [
    {
      "ID": "MoveToIA",
      "Status": "Enabled",
      "Filter": {},
      "Transitions": [
        {
          "Days": 90,
          "StorageClass": "STANDARD_IA"
        }
      ]
    },
    {
      "ID": "MoveToGlacier",
      "Status": "Enabled",
      "Filter": {},
      "Transitions": [
        {
          "Days": 365,
          "StorageClass": "GLACIER"
        }
      ]
    },
    {
      "ID": "DeleteOld",
      "Status": "Enabled",
      "Filter": {},
      "Expiration": {
        "Days": 2555
      }
    }
  ]
}
LIFECYCLE

aws s3api put-bucket-lifecycle-configuration \
  --bucket "$S3_BUCKET_NAME" \
  --lifecycle-configuration file:///tmp/lifecycle-policy.json \
  --region "$AWS_REGION" \
  --no-cli-pager \
  2>/dev/null || echo "   Lifecycle policy may already exist"

rm -f /tmp/lifecycle-policy.json

# Create folder structure
echo "   Creating folder structure..."
for folder in query-history metrics logs backups; do
  aws s3api put-object \
    --bucket "$S3_BUCKET_NAME" \
    --key "$folder/" \
    --region "$AWS_REGION" 2>/dev/null || true
done

echo "✅ Main bucket configured: s3://$S3_BUCKET_NAME"

# Create CloudWatch export bucket
echo "📊 Creating CloudWatch export bucket: $S3_CLOUDWATCH_BUCKET"
aws s3api create-bucket \
  --bucket "$S3_CLOUDWATCH_BUCKET" \
  --region "$AWS_REGION" \
  --create-bucket-configuration LocationConstraint="$AWS_REGION" \
  2>/dev/null || echo "   Bucket may already exist"

aws s3api put-bucket-encryption \
  --bucket "$S3_CLOUDWATCH_BUCKET" \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }' \
  --region "$AWS_REGION" 2>/dev/null || true

aws s3api put-public-access-block \
  --bucket "$S3_CLOUDWATCH_BUCKET" \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true" \
  --region "$AWS_REGION" 2>/dev/null || true

echo "✅ CloudWatch export bucket: s3://$S3_CLOUDWATCH_BUCKET"

# Save all IDs
cat > ../infrastructure-ids.txt <<EOF
AWS_REGION=$AWS_REGION
AWS_ACCOUNT_ID=$AWS_ACCOUNT_ID
VPC_ID=$VPC_ID
SUBNET_IDS=$SUBNET_IDS_COMMA
SECURITY_GROUP_ID=$SECURITY_GROUP_ID
NAMESPACE_ID=$NAMESPACE_ID
NAMESPACE_ARN=$NAMESPACE_ARN
ALB_ARN=$ALB_ARN
ALB_DNS_NAME=$ALB_DNS_NAME
TARGET_GROUP_ARN=$TARGET_GROUP_ARN
FRONTEND_TARGET_GROUP_ARN=$FRONTEND_TARGET_GROUP_ARN
S3_BUCKET_NAME=$S3_BUCKET_NAME
S3_CLOUDWATCH_BUCKET=$S3_CLOUDWATCH_BUCKET
EOF

echo ""
echo "=============================================="
echo "✅ Infrastructure setup complete!"
echo "=============================================="
echo ""
echo "📋 Created resources:"
echo "   - VPC, Subnets, Security Groups"
echo "   - ECS Cluster"
echo "   - Service Discovery Namespace"
echo "   - ALB with path-based routing:"
echo "       http://$ALB_DNS_NAME/              → Frontend"
echo "       http://$ALB_DNS_NAME/docs          → API (Swagger UI)"
echo "       http://$ALB_DNS_NAME/health         → API (health check)"
echo "       http://$ALB_DNS_NAME/api/*          → API (all API endpoints)"
echo "   - S3 Buckets: $S3_BUCKET_NAME, $S3_CLOUDWATCH_BUCKET"
echo ""
echo "📋 Saved to: aws/infrastructure-ids.txt"
echo ""
echo "Next steps:"
echo "1. Register task definitions: ./register-task-definitions.sh"
echo "2. Create ECS services: ./create-services.sh"

