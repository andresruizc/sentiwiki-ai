#!/bin/bash
# Clean task definition files by replacing account IDs and sensitive values with placeholders
# This script removes hardcoded account IDs, regions, and ALB DNS names from task definitions

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TASK_DEF_DIR="$SCRIPT_DIR/../task-definitions"

echo "🧹 Cleaning task definition files..."
echo "   Removing hardcoded account IDs, regions, and sensitive values"
echo ""

# Allow account ID and region to be passed as arguments, or auto-detect
ACCOUNT_ID="${1:-}"
REGION="${2:-}"

# Auto-detect if not provided as arguments
if [ -z "$ACCOUNT_ID" ] || [ -z "$REGION" ]; then
  echo "   Auto-detecting account ID and region from task definitions..."
  
  # Try to extract account ID from IAM role ARN pattern
  for task_file in "$TASK_DEF_DIR"/task-*.json; do
    if [ -f "$task_file" ]; then
      # Extract account ID from IAM role ARN (pattern: arn:aws:iam::ACCOUNT_ID:role/...)
      detected_account=$(grep -oP 'arn:aws:iam::\K[0-9]+' "$task_file" 2>/dev/null | head -1)
      if [ -n "$detected_account" ] && [ -z "$ACCOUNT_ID" ]; then
        ACCOUNT_ID="$detected_account"
      fi
      
      # Extract region from ECR URI (pattern: ACCOUNT.dkr.ecr.REGION.amazonaws.com)
      detected_region=$(grep -oP '[0-9]+\.dkr\.ecr\.\K[a-z0-9-]+' "$task_file" 2>/dev/null | head -1)
      if [ -n "$detected_region" ] && [ -z "$REGION" ]; then
        REGION="$detected_region"
      fi
      
      # Break if both found
      if [ -n "$ACCOUNT_ID" ] && [ -n "$REGION" ]; then
        break
      fi
    fi
  done
fi

# Validate that we have both values
if [ -z "$ACCOUNT_ID" ]; then
  echo "❌ Error: Account ID not found"
  echo ""
  echo "Usage: $0 [ACCOUNT_ID] [REGION]"
  echo "   Or ensure task definitions contain account ID in IAM role ARNs"
  exit 1
fi

if [ -z "$REGION" ]; then
  echo "❌ Error: Region not found"
  echo ""
  echo "Usage: $0 [ACCOUNT_ID] [REGION]"
  echo "   Or ensure task definitions contain region in ECR URIs"
  exit 1
fi

echo "   Using Account ID: $ACCOUNT_ID"
echo "   Using Region: $REGION"
echo ""

# Function to clean a task definition file
clean_task_definition() {
  local file=$1
  local filename=$(basename "$file")
  
  echo "   Cleaning $filename..."
  
  # Create backup
  cp "$file" "${file}.bak"
  
  # Replace account ID in various patterns:
  # - IAM role ARNs: arn:aws:iam::ACCOUNT_ID:role/...
  # - ECR image URIs: ACCOUNT_ID.dkr.ecr.REGION.amazonaws.com/...
  # - Secrets Manager ARNs: arn:aws:secretsmanager:REGION:ACCOUNT_ID:secret:...
  sed -i.tmp \
    -e "s|arn:aws:iam::${ACCOUNT_ID}:|arn:aws:iam::YOUR_ACCOUNT_ID:|g" \
    -e "s|${ACCOUNT_ID}\.dkr\.ecr\.${REGION}\.amazonaws\.com|YOUR_ACCOUNT_ID.dkr.ecr.YOUR_REGION.amazonaws.com|g" \
    -e "s|arn:aws:secretsmanager:${REGION}:${ACCOUNT_ID}:|arn:aws:secretsmanager:YOUR_REGION:YOUR_ACCOUNT_ID:|g" \
    -e "s|\"awslogs-region\": \"${REGION}\"|\"awslogs-region\": \"YOUR_REGION\"|g" \
    -e "s|\"value\": \"${REGION}\"|\"value\": \"YOUR_REGION\"|g" \
    "$file"
  
  # Remove backup files
  rm -f "${file}.bak" "${file}.tmp"
  
  echo "   ✅ $filename cleaned"
}

# Clean all task definition files
for task_file in "$TASK_DEF_DIR"/task-*.json; do
  if [ -f "$task_file" ]; then
    clean_task_definition "$task_file"
  fi
done

# Special handling for frontend: replace ALB DNS name
FRONTEND_FILE="$TASK_DEF_DIR/task-frontend.json"
if [ -f "$FRONTEND_FILE" ]; then
  echo ""
  echo "   Cleaning frontend ALB DNS name..."
  
  # Use Python to replace ALB DNS name more safely
  python3 << EOF
import json
import re

file_path = '$FRONTEND_FILE'

try:
    with open(file_path, 'r') as f:
        task_def = json.load(f)
    
    updated = False
    for container_def in task_def.get('containerDefinitions', []):
        if container_def.get('name') == 'frontend':
            for env_var in container_def.get('environment', []):
                if env_var.get('name') == 'NEXT_PUBLIC_API_URL':
                    # Replace any ALB DNS name pattern with placeholder
                    old_value = env_var['value']
                    # Match patterns like http://something-1234567890.region.elb.amazonaws.com
                    if re.match(r'^http://.*\.elb\.amazonaws\.com', old_value):
                        env_var['value'] = 'http://placeholder-alb-dns-name'
                        print(f'   Updated NEXT_PUBLIC_API_URL: {old_value} → http://placeholder-alb-dns-name')
                        updated = True
                    break
    
    if updated:
        with open(file_path, 'w') as f:
            json.dump(task_def, f, indent=2)
        print('   ✅ Frontend ALB DNS name cleaned')
    else:
        print('   ℹ️  No ALB DNS name found to clean')
        
except Exception as e:
    print(f'   ⚠️  Could not clean frontend ALB DNS name: {e}')
EOF
fi

echo ""
echo "✅ All task definition files cleaned!"
echo ""
echo "📝 Placeholders used:"
echo "   - YOUR_ACCOUNT_ID (replaces account ID)"
echo "   - YOUR_REGION (replaces region)"
echo "   - http://placeholder-alb-dns-name (replaces ALB DNS name)"
echo ""
echo "💡 These will be automatically replaced when running:"
echo "   ./register-task-definitions.sh"

