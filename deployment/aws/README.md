# AWS ECS Deployment Configuration

This directory contains all the configuration files and scripts needed to deploy the ESA IAGEN application to AWS ECS.

**Minimal Setup**: This deployment includes only the 3 essential services:
- **Qdrant** (vector database)
- **API** (FastAPI backend)
- **Frontend** (Next.js UI)

Prometheus and Grafana (monitoring) are optional and can be added later if needed.

## 📁 Directory Structure

```
aws/
├── README.md                          # This file
├── infrastructure-ids.txt              # Generated file with infrastructure IDs (created by setup script)
├── task-definitions/                  # ECS task definitions
│   ├── task-qdrant.json              # Qdrant vector database
│   ├── task-api.json                 # FastAPI backend
│   ├── task-frontend.json            # Next.js frontend
│   ├── task-prometheus.json           # Prometheus monitoring
│   └── task-grafana.json             # Grafana dashboards
├── scripts/                          # Core setup and deployment scripts
│   ├── setup-infrastructure.sh       # One-time infrastructure setup
│   ├── register-task-definitions.sh # Register task definitions
│   ├── create-services.sh            # Create ECS services
│   ├── cleanup-infrastructure.sh     # Remove all infrastructure (cleanup)
│   ├── force-redeploy-service.sh     # Force service redeployment
│   ├── sync-api-cors.sh              # Sync API CORS with frontend IP
│   ├── get-service-ips.sh            # Get service URLs and IPs
│   ├── check-service-status.sh       # Check service status
│   ├── setup-autoscaling.sh          # Configure auto-scaling
│   └── add-monitoring.sh             # Add Prometheus/Grafana monitoring
├── helpers/                          # Troubleshooting and diagnostic scripts
│   ├── diagnose-alb-connection.sh     # Diagnose ALB-frontend connection issues
│   ├── diagnose-api-routing.sh       # Diagnose API routing issues
│   ├── diagnose-frontend.sh          # Diagnose frontend health issues
│   ├── diagnose-service-communication.sh # Diagnose service-to-service communication
│   ├── fix-security-groups.sh        # Harden security group rules
│   ├── verify-frontend-build.sh       # Verify frontend build configuration
│   └── check-subnet-public.sh        # Check if subnets are public
└── prometheus/                       # Prometheus configuration for ECS
    └── prometheus.yml                # Prometheus config using service discovery
```

## 📂 Scripts Overview

### `scripts/` - Core Operations
Contains essential scripts for setup, deployment, and daily operations:
- **Setup**: `setup-infrastructure.sh`, `register-task-definitions.sh`, `create-services.sh`
- **Deployment**: `force-redeploy-service.sh`, `sync-api-cors.sh`
- **Monitoring**: `setup-autoscaling.sh`, `add-monitoring.sh`
- **Utilities**: `get-service-ips.sh`, `check-service-status.sh`
- **Cleanup**: `cleanup-infrastructure.sh`

### `helpers/` - Troubleshooting
Contains diagnostic and fix scripts for troubleshooting issues:
- **Diagnostics**: `diagnose-*.sh` scripts for comprehensive issue analysis
- **Fixes**: `fix-security-groups.sh` for security hardening
- **Verification**: `verify-frontend-build.sh`, `check-subnet-public.sh`

**When to use helpers**: Use these scripts when you encounter issues and need to diagnose or fix specific problems. The diagnostic scripts provide detailed analysis and recommendations.

## 🚀 Quick Start

### Prerequisites

1. **AWS CLI installed and configured**
   ```bash
   aws --version
   aws configure
   ```

2. **AWS Account with appropriate permissions**
   - ECS, ECR, VPC, Service Discovery, IAM permissions

3. **GitHub Secrets configured** (for CI/CD)
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `AWS_REGION`
   - `AWS_ACCOUNT_ID`

### Step 1: Set Up Infrastructure (One-Time)

This creates all necessary AWS resources:

```bash
cd deployment/aws/scripts
./setup-infrastructure.sh
```

This script creates:
- ECS Cluster
- CloudWatch Log Group
- VPC and Subnets (uses default VPC)
- Security Groups
- Service Discovery Namespace
- IAM Roles

**Output**: `infrastructure-ids.txt` with all resource IDs

### Step 2: Register Task Definitions

Register all task definitions with ECS:

```bash
cd aws/scripts
./register-task-definitions.sh
```

This registers task definitions for the 3 essential services:
- Qdrant
- API
- Frontend

**Note**: Prometheus and Grafana task definitions are available but commented out. Uncomment them in the script if you want to add monitoring later.

**Important**: Before running, make sure to:
1. Set up AWS Secrets Manager for API keys (see Step 4)
2. Create S3 bucket for query logging (see Step 4)
3. Update task definitions if needed:
   - **API**: Currently configured with 4 vCPU / 8 GB (required for ML models: BGE-small 130MB + reranker 130MB)
   - **Frontend/Qdrant**: 0.25 vCPU / 512 MB (can be adjusted if needed)
4. Update image URLs in task definitions with your AWS Account ID and Region

### Step 3: Create ECS Services

Create ECS services that keep containers running:

```bash
cd aws/scripts
./create-services.sh
```

This creates services for the 3 essential containers (Qdrant, API, Frontend).

**Note**: Prometheus and Grafana services are available but commented out. Uncomment them in the script if you want to add monitoring later.

### Step 4: Set Up AWS Secrets Manager and S3 Bucket

Before deploying, you need to:

**1. Store API keys in AWS Secrets Manager:**

```bash
# Store Anthropic API key
aws secretsmanager create-secret \
  --name esa-iagen/ANTHROPIC_API_KEY \
  --secret-string "your-anthropic-api-key" \
  --region YOUR_REGION

# Store OpenAI API key (optional)
aws secretsmanager create-secret \
  --name esa-iagen/OPENAI_API_KEY \
  --secret-string "your-openai-api-key" \
  --region YOUR_REGION
```

**Important**: The task definitions reference these secrets. Make sure the secret names match.

**2. Create S3 bucket for query logging (optional but recommended):**

```bash
# Create S3 bucket for storing query logs
aws s3 mb s3://esa-iagen-data --region YOUR_REGION

# Enable versioning (optional)
aws s3api put-bucket-versioning \
  --bucket esa-iagen-data \
  --versioning-configuration Status=Enabled \
  --region YOUR_REGION
```

**Note**: The API task definition includes S3 logging configuration. If you don't create the bucket, logging will be disabled but the service will still work.

### Step 5: Deploy via GitHub Actions

Once everything is set up, push to `main` branch:

```bash
git push origin main
```

GitHub Actions will:
1. Run tests (Phase 1)
2. Build Docker images (Phase 2)
3. Push images to ECR (Phase 3)
4. Deploy to ECS (Phase 4) ← **Automatic!**

**Note**: The first deployment may take longer (7-11 minutes) because:
- Docker images are built from scratch
- Models are downloaded on first container start (BGE-small: 130MB, reranker: 130MB)
- Health checks wait for models to load (180 second start period for API)

## 📋 Task Definitions

### Essential Services

#### Qdrant (`task-qdrant.json`)
- **Image**: `qdrant/qdrant:latest` (public)
- **CPU**: 256 (0.25 vCPU)
- **Memory**: 512 MB
- **Ports**: 6333 (HTTP), 6334 (gRPC)
- **Storage**: Ephemeral (data lost on restart)

#### API (`task-api.json`)
- **Image**: `YOUR_ACCOUNT_ID.dkr.ecr.YOUR_REGION.amazonaws.com/esa-iagen-api:latest`
- **CPU**: 4096 (4 vCPU) - **Production configuration** for ML models (BGE-small: 130MB, reranker: 130MB)
- **Memory**: 8192 MB (8 GB) - Required for embedding model + reranker + LLM client
- **Port**: 8000
- **Environment**: 
  - Connects to Qdrant via service discovery (`qdrant.esa-iagen.local`)
  - S3 logging enabled (`esa-iagen-data` bucket)
  - CORS configured for frontend IPs
- **Secrets**: API keys from AWS Secrets Manager (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`)
- **Health Check**: 180 second start period (allows time for model loading: BGE-small ~1-2s, reranker ~1-2s)
- **Logging**: CloudWatch Logs (`/ecs/esa-iagen`), S3 query logs (`esa-iagen-data` bucket)

#### Frontend (`task-frontend.json`)
- **Image**: `YOUR_ACCOUNT_ID.dkr.ecr.YOUR_REGION.amazonaws.com/esa-iagen-frontend:latest`
- **CPU**: 256 (0.25 vCPU)
- **Memory**: 512 MB
- **Port**: 3000
- **Environment**: 
  - API URL via ALB (Application Load Balancer DNS name)
  - `NEXT_PUBLIC_API_URL` set to ALB endpoint (e.g., `http://esa-iagen-api-alb-xxx.elb.amazonaws.com`)
  - `NEXT_PUBLIC_ENV=production`

### Optional Services (Monitoring)

#### Prometheus (`task-prometheus.json`)
- **Image**: `prom/prometheus:latest` (public)
- **CPU**: 256 (0.25 vCPU)
- **Memory**: 512 MB
- **Port**: 9090
- **Storage**: Ephemeral (data lost on restart)
- **Status**: Available but not deployed by default

#### Grafana (`task-grafana.json`)
- **Image**: `grafana/grafana:latest` (public)
- **CPU**: 256 (0.25 vCPU)
- **Memory**: 512 MB
- **Port**: 3000
- **Storage**: Ephemeral (data lost on restart)
- **Status**: Available but not deployed by default

## 🔧 Service Discovery

Services find each other using DNS names:
- **Qdrant**: `qdrant.esa-iagen.local:6333`
- **API**: `api.esa-iagen.local:8000`
- **Frontend**: `frontend.esa-iagen.local:3000`
- **Prometheus**: `prometheus.esa-iagen.local:9090`
- **Grafana**: `grafana.esa-iagen.local:3000`

These are resolved automatically within the VPC.

## 📊 Monitoring

### View Logs

```bash
# Stream logs from all services
aws logs tail /ecs/esa-iagen --follow --region YOUR_REGION

# View logs for specific service
aws logs tail /ecs/esa-iagen --follow --filter-pattern "api" --region YOUR_REGION
```

### Check Service Status

```bash
# List all services
aws ecs list-services --cluster esa-iagen-cluster --region YOUR_REGION

# Describe service
aws ecs describe-services \
  --cluster esa-iagen-cluster \
  --services esa-iagen-api-service \
  --region YOUR_REGION
```

### View Running Tasks

```bash
# List tasks
aws ecs list-tasks --cluster esa-iagen-cluster --region YOUR_REGION

# Describe task
TASK_ARN=$(aws ecs list-tasks --cluster esa-iagen-cluster --service-name esa-iagen-api-service --query 'taskArns[0]' --output text --region YOUR_REGION)
aws ecs describe-tasks --cluster esa-iagen-cluster --tasks $TASK_ARN --region YOUR_REGION
```

## 🔄 Manual Deployment

If you need to manually trigger a deployment:

```bash
cd aws/scripts

# Force redeploy a service
./force-redeploy-service.sh esa-iagen-api-service
./force-redeploy-service.sh esa-iagen-frontend-service

# Or use AWS CLI directly
aws ecs update-service \
  --cluster esa-iagen-cluster \
  --service esa-iagen-api-service \
  --force-new-deployment \
  --region YOUR_REGION
```

### Get Service URLs

```bash
cd aws/scripts
./get-service-ips.sh
```

This shows:
- ALB URLs for API and Frontend
- Direct IPs for internal services (Qdrant, Prometheus, Grafana)
- Service status

## 🛠️ Troubleshooting

### Quick Diagnostics

Use the diagnostic scripts in `helpers/` for comprehensive troubleshooting:

```bash
cd aws/helpers

# Diagnose ALB-frontend connection issues
./diagnose-alb-connection.sh

# Diagnose API routing issues
./diagnose-api-routing.sh

# Diagnose frontend health issues
./diagnose-frontend.sh

# Diagnose service-to-service communication
./diagnose-service-communication.sh

# Check if subnets are public
./check-subnet-public.sh

# Verify frontend build configuration
./verify-frontend-build.sh
```

### Common Issues

#### Service Won't Start

```bash
# Use the diagnostic script
cd aws/scripts
./check-service-status.sh esa-iagen-api-service

# Or check service events manually
aws ecs describe-services \
  --cluster esa-iagen-cluster \
  --services esa-iagen-api-service \
  --region YOUR_REGION \
  --query 'services[0].events[:5]'
```

#### Container Keeps Restarting

```bash
# Check logs
aws logs tail /ecs/esa-iagen --follow --region YOUR_REGION

# Check task status
TASK_ARN=$(aws ecs list-tasks --cluster esa-iagen-cluster --service-name esa-iagen-api-service --query 'taskArns[0]' --output text --region YOUR_REGION)
aws ecs describe-tasks --cluster esa-iagen-cluster --tasks $TASK_ARN --region YOUR_REGION
```

#### Services Can't Find Each Other

```bash
# Use the diagnostic script
cd aws/helpers
./diagnose-service-communication.sh

# Or verify service discovery manually
aws servicediscovery list-services \
  --filters "Name=NAMESPACE_ID,Values=YOUR_NAMESPACE_ID" \
  --region YOUR_REGION
```

#### Frontend Can't Connect to API

```bash
# Sync CORS with current frontend IP
cd aws/scripts
./sync-api-cors.sh

# Diagnose ALB connection
cd ../helpers
./diagnose-alb-connection.sh
```


## 💰 Cost Estimate

### Free Tier (First 12 Months)
- ECS Fargate: 20 GB-hours/month ✅ Free
- ECR: 500MB storage/month ✅ Free
- CloudWatch Logs: 5GB/month ✅ Free

### After Free Tier
- **ECS Fargate** (3 essential services): ~$120-150/month
  - API: ~$100/month (4 vCPU, 8 GB - required for ML models)
  - Frontend: ~$8/month (0.25 vCPU, 512 MB)
  - Qdrant: ~$15/month (0.25 vCPU, 512 MB)
- **ECR**: ~$0.10/GB/month (usually free within 500MB)
- **CloudWatch**: Usually within free tier
- **ALB**: ~$20/month (Application Load Balancer)

**Total**: ~$140-170/month for essential services

**With monitoring** (Prometheus + Grafana): +$6/month ≈ $146-176/month total

**Note**: API requires 4 vCPU / 8 GB because it runs ML models (BGE-small embedding: 130MB, reranker: 130MB) which need significant memory and CPU for inference.

## 🧹 Cleanup (Remove All Infrastructure)

To remove all AWS infrastructure and avoid ongoing costs:

```bash
cd aws/scripts
./cleanup-infrastructure.sh
```

**What it deletes:**
- ✅ ECS Services (Qdrant, API, Frontend)
- ✅ ECS Task Definitions
- ✅ Service Discovery (services and namespace)
- ✅ Security Group and rules
- ✅ CloudWatch Log Group
- ✅ ECS Cluster

**What it does NOT delete:**
- ⚠️ ECR repositories and images (you need to delete manually if desired)
- ⚠️ IAM roles (may be used by other resources)
- ⚠️ Network resources (persistent, account-level):
  - VPC, Subnets, Route Tables, Internet Gateway
  - **Network changes persist** - once subnets are public, they stay public

**Note**: Network troubleshooting scripts are in `helpers/`. `setup-infrastructure.sh` now automatically makes subnets public if needed, so you rarely need to run them manually. Once subnets are public in your account, they remain public across cleanup/setup cycles.

**To delete ECR repositories:**
```bash
aws ecr delete-repository --repository-name esa-iagen-api --force --region YOUR_REGION
aws ecr delete-repository --repository-name esa-iagen-frontend --force --region YOUR_REGION
```

## 📚 Additional Resources

- [Phase 4 Documentation](../docs/deployment/07_PHASE4_ECS_DEPLOYMENT.md)
- [AWS ECS Deployment Guide](../docs/deployment/05_AWS_ECS_DEPLOYMENT.md)
- [CORS Configuration in ECS](../docs/architecture/CORS_IN_ECS.md)
- [Adding Monitoring Later](ADD_MONITORING_LATER.md)
- [AWS ECS Documentation](https://docs.aws.amazon.com/ecs/)

## ✅ Next Steps

After Phase 4 is complete:

1. **Set up Auto Scaling**: Scale services based on CPU/memory
2. **Add CloudWatch Alarms**: Monitor and alert on issues
3. **Use Custom Domain**: Point your domain to service IPs
4. **Set up CI/CD for staging**: Deploy `develop` branch to staging environment

