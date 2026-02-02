#!/bin/bash
# Register ECS Task Definitions
# This script registers all task definitions with ECS

set -e

# Disable AWS CLI pager to prevent hanging
export AWS_PAGER=""

# Load infrastructure IDs
if [ ! -f "../infrastructure-ids.txt" ]; then
  echo "❌ infrastructure-ids.txt not found. Run setup-infrastructure.sh first."
  exit 1
fi

source ../infrastructure-ids.txt

echo "📝 Registering ECS task definitions..."
echo "   Region: $AWS_REGION"
echo "   Account ID: $AWS_ACCOUNT_ID"
echo ""

# Function to replace placeholders in task definition
replace_placeholders() {
  local file=$1
  sed -i.bak \
    -e "s/YOUR_ACCOUNT_ID/$AWS_ACCOUNT_ID/g" \
    -e "s/YOUR_REGION/$AWS_REGION/g" \
    "$file"
  rm -f "${file}.bak"
}

# Function to update frontend task definition with ALB DNS name
update_frontend_with_alb() {
  local file=$1
  
  if [ -n "$ALB_DNS_NAME" ] && [ "$ALB_DNS_NAME" != "None" ]; then
    # Use Python to update JSON (more robust than sed)
    python3 << EOF
import json
import sys

file_path = '$file'
alb_dns = '$ALB_DNS_NAME'
new_api_url = f"http://{alb_dns}"

try:
    with open(file_path, 'r') as f:
        task_def = json.load(f)

    updated = False
    for container_def in task_def['containerDefinitions']:
        if container_def['name'] == 'frontend':
            for env_var in container_def.get('environment', []):
                if env_var['name'] == 'NEXT_PUBLIC_API_URL':
                    old_value = env_var['value']
                    env_var['value'] = new_api_url
                    print(f'   Updated NEXT_PUBLIC_API_URL: {old_value} → {new_api_url}')
                    updated = True
                    break
            if not updated:
                # If NEXT_PUBLIC_API_URL not found, add it
                if 'environment' not in container_def:
                    container_def['environment'] = []
                container_def['environment'].append({'name': 'NEXT_PUBLIC_API_URL', 'value': new_api_url})
                print(f'   Added NEXT_PUBLIC_API_URL: {new_api_url}')
                updated = True
            break

    if updated:
        with open(file_path, 'w') as f:
            json.dump(task_def, f, indent=2)
        print('   ✅ Frontend task definition updated with ALB DNS name')
    else:
        print('   ⚠️  Could not find frontend container in task definition')

except Exception as e:
    print(f'   ⚠️  Could not update frontend task definition: {e}')
    # Don't exit - continue with original file
EOF
  else
    echo "   ⚠️  ALB_DNS_NAME not found, skipping frontend API URL update"
  fi
}

# Register Qdrant
echo "📦 Registering Qdrant task definition..."
replace_placeholders "../task-definitions/task-qdrant.json"

# Register task definition and catch PassRole errors
REGISTER_OUTPUT=$(aws ecs register-task-definition \
  --cli-input-json file://../task-definitions/task-qdrant.json \
  --region $AWS_REGION \
  --query 'taskDefinition.taskDefinitionArn' \
  --output text 2>&1)
REGISTER_EXIT=$?

if [ $REGISTER_EXIT -ne 0 ]; then
  if echo "$REGISTER_OUTPUT" | grep -q "AccessDeniedException.*PassRole"; then
    echo ""
    echo "❌ Error: Missing IAM permission 'iam:PassRole'"
    echo ""
    echo "   Your IAM user needs permission to pass the role to ECS."
    echo "   See: ../IAM_PERMISSIONS_REQUIRED.md for instructions"
    echo ""
    echo "   Quick fix (run as admin):"
    echo "   aws iam put-user-policy --user-name github-actions-ci-cd --policy-name PassRoleForECS --policy-document '{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Action\":\"iam:PassRole\",\"Resource\":\"arn:aws:iam::$AWS_ACCOUNT_ID:role/ecsTaskExecutionRole\"}]}'"
    echo ""
  else
    echo "❌ Error registering task definition:"
    echo "$REGISTER_OUTPUT"
  fi
  exit 1
fi

echo "✅ Qdrant task definition registered"

# Register API
echo "📦 Registering API task definition..."
replace_placeholders "../task-definitions/task-api.json"

# Note: CORS sync with frontend IP is handled separately
# Run ./sync-api-cors.sh after services are running
aws ecs register-task-definition \
  --cli-input-json file://../task-definitions/task-api.json \
  --region $AWS_REGION \
  --query 'taskDefinition.taskDefinitionArn' \
  --output text
echo "✅ API task definition registered"

# Register Frontend
echo "📦 Registering Frontend task definition..."
replace_placeholders "../task-definitions/task-frontend.json"

# Update frontend task definition with ALB DNS name (if ALB exists)
if [ -n "$ALB_DNS_NAME" ] && [ "$ALB_DNS_NAME" != "None" ]; then
  echo "   Updating frontend API URL to use ALB: $ALB_DNS_NAME"
  update_frontend_with_alb "../task-definitions/task-frontend.json"
fi
aws ecs register-task-definition \
  --cli-input-json file://../task-definitions/task-frontend.json \
  --region $AWS_REGION \
  --query 'taskDefinition.taskDefinitionArn' \
  --output text
echo "✅ Frontend task definition registered"

# Monitoring: Prometheus and Grafana (optional but recommended)
# Set SKIP_MONITORING=true to skip monitoring deployment
if [ "${SKIP_MONITORING:-false}" != "true" ]; then
  echo ""
  echo "📊 Registering monitoring task definitions..."
  
  echo "📦 Registering Prometheus task definition..."
  replace_placeholders "../task-definitions/task-prometheus.json"
  aws ecs register-task-definition \
    --cli-input-json file://../task-definitions/task-prometheus.json \
    --region $AWS_REGION \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text
  echo "✅ Prometheus task definition registered"

  echo "📦 Registering Grafana task definition..."
  replace_placeholders "../task-definitions/task-grafana.json"
  aws ecs register-task-definition \
    --cli-input-json file://../task-definitions/task-grafana.json \
    --region $AWS_REGION \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text
  echo "✅ Grafana task definition registered"
else
  echo ""
  echo "⏭️  Skipping monitoring (SKIP_MONITORING=true)"
fi

echo ""
echo "✅ Task definitions registered successfully!"
echo "   - Qdrant, API, Frontend (essential)"
if [ "${SKIP_MONITORING:-false}" != "true" ]; then
  echo "   - Prometheus, Grafana (monitoring)"
fi
echo ""
echo "💡 Tip: To skip monitoring, run: SKIP_MONITORING=true ./register-task-definitions.sh"

