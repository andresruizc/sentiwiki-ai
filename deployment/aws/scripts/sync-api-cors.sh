#!/bin/bash
# Sync API CORS origins with current frontend IP
# This ensures CORS allows requests from the current frontend IP
# Run this after frontend service starts or if frontend IP changes

set -e

export AWS_PAGER=""

# Load configuration
if [ -f "../infrastructure-ids.txt" ]; then
  source ../infrastructure-ids.txt
else
  echo "❌ infrastructure-ids.txt not found. Run setup-infrastructure.sh first."
  exit 1
fi

CLUSTER="esa-iagen-cluster"
REGION=$AWS_REGION
FRONTEND_SERVICE_NAME="esa-iagen-frontend-service"
API_TASK_DEF_FILE="../task-definitions/task-api.json"

echo "🔄 Syncing API CORS origins with current frontend IP..."
echo "   Cluster: $CLUSTER"
echo "   Region: $REGION"
echo ""

# 1. Get current frontend service public IP
echo "1️⃣  Getting current frontend service public IP..."
FRONTEND_TASK_ARN=$(aws ecs list-tasks \
  --cluster $CLUSTER \
  --service-name $FRONTEND_SERVICE_NAME \
  --desired-status RUNNING \
  --region $REGION \
  --query 'taskArns[0]' \
  --output text 2>/dev/null || echo "")

if [ -z "$FRONTEND_TASK_ARN" ] || [ "$FRONTEND_TASK_ARN" = "None" ] || [ "$FRONTEND_TASK_ARN" = "null" ]; then
  echo "❌ No running frontend tasks found for service '$FRONTEND_SERVICE_NAME'. Is the frontend service running?"
  exit 1
fi

ENI_ID=$(aws ecs describe-tasks \
  --cluster $CLUSTER \
  --tasks $FRONTEND_TASK_ARN \
  --region $REGION \
  --query 'tasks[0].attachments[0].details[?name==`networkInterfaceId`].value' \
  --output text 2>/dev/null || echo "")

if [ -z "$ENI_ID" ] || [ "$ENI_ID" = "None" ] || [ "$ENI_ID" = "null" ]; then
  echo "❌ Could not get network interface for frontend task '$FRONTEND_TASK_ARN'."
  exit 1
fi

CURRENT_FRONTEND_IP=$(aws ec2 describe-network-interfaces \
  --network-interface-ids $ENI_ID \
  --region $REGION \
  --query 'NetworkInterfaces[0].Association.PublicIp' \
  --output text 2>/dev/null || echo "")

if [ -z "$CURRENT_FRONTEND_IP" ] || [ "$CURRENT_FRONTEND_IP" = "None" ] || [ "$CURRENT_FRONTEND_IP" = "null" ]; then
  echo "❌ Frontend service '$FRONTEND_SERVICE_NAME' does not have a public IP. Ensure it's in a public subnet."
  exit 1
fi

FRONTEND_ORIGIN="http://${CURRENT_FRONTEND_IP}:3000"
echo "✅ Current frontend public IP: $CURRENT_FRONTEND_IP (Origin: $FRONTEND_ORIGIN)"
echo ""

# 2. Read current CORS origins from task definition
echo "2️⃣  Reading current CORS configuration..."
CURRENT_CORS=$(python3 -c "
import json
import sys

file_path = '$API_TASK_DEF_FILE'

try:
    with open(file_path, 'r') as f:
        task_def = json.load(f)

    for container_def in task_def['containerDefinitions']:
        if container_def['name'] == 'api':
            for env_var in container_def.get('environment', []):
                if env_var['name'] == 'API__CORS_ORIGINS':
                    print(env_var['value'])
                    break
            break
except Exception as e:
    print('', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null || echo "")

if [ -z "$CURRENT_CORS" ]; then
  echo "⚠️  No CORS configuration found in task definition. Will add it."
  CURRENT_CORS=""
fi

# 3. Check if frontend origin is already in CORS list
if echo "$CURRENT_CORS" | grep -q "$FRONTEND_ORIGIN"; then
  echo "✅ Frontend origin '$FRONTEND_ORIGIN' is already in CORS allowlist."
  echo "   No update needed."
  exit 0
fi

echo "📝 Current CORS origins: $CURRENT_CORS"
echo "📝 Adding frontend origin: $FRONTEND_ORIGIN"
echo ""

# 4. Update CORS origins in task definition
echo "3️⃣  Updating '$API_TASK_DEF_FILE' with new frontend origin..."

python3 << EOF
import json
import sys

file_path = '$API_TASK_DEF_FILE'
frontend_origin = '$FRONTEND_ORIGIN'
current_cors = '$CURRENT_CORS'

try:
    with open(file_path, 'r') as f:
        task_def = json.load(f)

    updated = False
    for container_def in task_def['containerDefinitions']:
        if container_def['name'] == 'api':
            for env_var in container_def.get('environment', []):
                if env_var['name'] == 'API__CORS_ORIGINS':
                    # Parse current CORS origins
                    current_origins = [o.strip() for o in current_cors.split(',') if o.strip()] if current_cors else []
                    
                    # Add frontend origin if not already present
                    if frontend_origin not in current_origins:
                        current_origins.append(frontend_origin)
                    
                    # Keep localhost origins for development
                    localhost_origins = [
                        'http://localhost:3000',
                        'http://localhost:3001',
                        'http://127.0.0.1:3000',
                        'http://127.0.0.1:3001'
                    ]
                    
                    # Combine: frontend IP + localhost origins
                    all_origins = [frontend_origin] + localhost_origins
                    # Remove duplicates while preserving order
                    seen = set()
                    unique_origins = []
                    for origin in all_origins:
                        if origin not in seen:
                            seen.add(origin)
                            unique_origins.append(origin)
                    
                    new_cors_value = ','.join(unique_origins)
                    old_value = env_var['value']
                    env_var['value'] = new_cors_value
                    print(f'   Updated API__CORS_ORIGINS:')
                    print(f'   Old: {old_value}')
                    print(f'   New: {new_cors_value}')
                    updated = True
                    break
            
            if not updated:
                # If API__CORS_ORIGINS not found, add it
                if 'environment' not in container_def:
                    container_def['environment'] = []
                
                # Default CORS origins: frontend IP + localhost
                default_origins = [
                    frontend_origin,
                    'http://localhost:3000',
                    'http://localhost:3001',
                    'http://127.0.0.1:3000',
                    'http://127.0.0.1:3001'
                ]
                cors_value = ','.join(default_origins)
                container_def['environment'].append({
                    'name': 'API__CORS_ORIGINS',
                    'value': cors_value
                })
                print(f'   Added API__CORS_ORIGINS: {cors_value}')
                updated = True
            break

    if updated:
        with open(file_path, 'w') as f:
            json.dump(task_def, f, indent=2)
        print('✅ Task definition file updated successfully.')
    else:
        print('⚠️  Could not find API container in task definition.')
        sys.exit(1)

except FileNotFoundError:
    print(f'❌ Error: Task definition file not found at {file_path}')
    sys.exit(1)
except json.JSONDecodeError:
    print(f'❌ Error: Invalid JSON in {file_path}')
    sys.exit(1)
except Exception as e:
    print(f'❌ An unexpected error occurred: {e}')
    sys.exit(1)
EOF

if [ $? -ne 0 ]; then
  echo "❌ Failed to update task definition file."
  exit 1
fi
echo ""

# 5. Register the updated task definition and capture the new revision
echo "4️⃣  Registering the updated API task definition..."

# Register the API task definition directly and capture the new revision
NEW_TASK_DEF_ARN=$(aws ecs register-task-definition \
  --cli-input-json file://$API_TASK_DEF_FILE \
  --region $REGION \
  --query 'taskDefinition.taskDefinitionArn' \
  --output text 2>&1)

if [ $? -ne 0 ] || [ -z "$NEW_TASK_DEF_ARN" ] || [ "$NEW_TASK_DEF_ARN" = "None" ]; then
  echo "❌ Failed to register task definition"
  echo "   Error: $NEW_TASK_DEF_ARN"
  exit 1
fi

# Extract revision number and family name from ARN for display
NEW_REVISION=$(echo "$NEW_TASK_DEF_ARN" | grep -oE '[0-9]+$')
TASK_DEF_FAMILY=$(echo "$NEW_TASK_DEF_ARN" | grep -oE 'task-definition/[^:]+' | cut -d'/' -f2)
TASK_DEF_SHORT="${TASK_DEF_FAMILY}:${NEW_REVISION}"

echo "✅ API task definition registered (revision: $NEW_REVISION)"
echo "   ARN: $NEW_TASK_DEF_ARN"
echo "   Short format: $TASK_DEF_SHORT"
echo ""

# 6. Force a new deployment with the SPECIFIC new task definition revision
echo "5️⃣  Forcing a new deployment of the API service with revision $NEW_REVISION..."

# First, check current service status
echo "   Checking current service status..."
CURRENT_TASK_DEF=$(aws ecs describe-services \
  --cluster $CLUSTER \
  --services esa-iagen-api-service \
  --region $REGION \
  --query 'services[0].taskDefinition' \
  --output text 2>/dev/null || echo "")

if [ -n "$CURRENT_TASK_DEF" ]; then
  echo "   Current task definition: $CURRENT_TASK_DEF"
  CURRENT_REVISION=$(echo "$CURRENT_TASK_DEF" | grep -oE '[0-9]+$' || echo "")
  if [ "$CURRENT_REVISION" = "$NEW_REVISION" ]; then
    echo "   ⚠️  Service is already using revision $NEW_REVISION, but forcing new deployment anyway..."
  fi
fi

# Update service with new task definition using short format (more reliable)
echo "   Updating service to use task definition: $TASK_DEF_SHORT..."
UPDATE_RESULT=$(aws ecs update-service \
  --cluster $CLUSTER \
  --service esa-iagen-api-service \
  --task-definition "$TASK_DEF_SHORT" \
  --force-new-deployment \
  --region $REGION 2>&1)

UPDATE_EXIT_CODE=$?

if [ $UPDATE_EXIT_CODE -ne 0 ]; then
  echo "❌ Failed to update service"
  echo "   Error: $UPDATE_RESULT"
  exit 1
fi

# Verify the update was successful by checking the service again
echo "   Verifying deployment was initiated..."
sleep 3

DEPLOYMENT_STATUS=$(aws ecs describe-services \
  --cluster $CLUSTER \
  --services esa-iagen-api-service \
  --region $REGION \
  --query 'services[0].deployments[?status==`PRIMARY`].{TaskDef:taskDefinition,Status:status,Desired:desiredCount,Running:runningCount}' \
  --output json 2>/dev/null || echo "[]")

CURRENT_TASK_DEF_AFTER=$(aws ecs describe-services \
  --cluster $CLUSTER \
  --services esa-iagen-api-service \
  --region $REGION \
  --query 'services[0].taskDefinition' \
  --output text 2>/dev/null || echo "")

# Check if the task definition was actually updated
if echo "$CURRENT_TASK_DEF_AFTER" | grep -q ":$NEW_REVISION$"; then
  echo "✅ API service deployment triggered successfully with revision $NEW_REVISION!"
  echo "   Current task definition: $CURRENT_TASK_DEF_AFTER"
else
  echo "⚠️  Warning: Service update command succeeded, but task definition may not have changed yet."
  echo "   Expected: *:$NEW_REVISION"
  echo "   Current: $CURRENT_TASK_DEF_AFTER"
  echo "   This may be normal if the deployment is still initializing."
fi

echo ""
echo "⏳ The service will now deploy the new task definition (revision $NEW_REVISION)."
echo "   This may take 1-2 minutes. Monitor its status with:"
echo "   aws ecs describe-services --cluster $CLUSTER --services esa-iagen-api-service --region $REGION"
echo ""
echo "💡 If the deployment doesn't start, you can force it manually:"
  echo "   cd deployment/aws/scripts && ./force-redeploy-service.sh esa-iagen-api-service"
echo ""
echo "💡 Or verify deployment status:"
  echo "   cd deployment/aws/scripts && ./verify-api-deployment.sh"
echo ""
echo "💡 Once the new task is running, CORS will allow requests from: $FRONTEND_ORIGIN"

