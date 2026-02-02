# Phase 4 Quick Start Guide

## ✅ What's Been Created

Phase 4 is now ready! Here's what has been set up:

**Complete Setup**: 3 essential services (Qdrant, API, Frontend) + Monitoring (Prometheus/Grafana) included by default. All accessible via Application Load Balancer (ALB) with path-based routing.

### 📁 Files Created

1. **Task Definitions** (`deployment/aws/task-definitions/`)
   - `task-qdrant.json` - Qdrant vector database (essential)
   - `task-api.json` - FastAPI backend (essential)
   - `task-frontend.json` - Next.js frontend (essential)
   - `task-prometheus.json` - Prometheus monitoring (included by default)
   - `task-grafana.json` - Grafana dashboards (included by default)

2. **Setup Scripts** (`deployment/aws/scripts/`)
   - `setup-infrastructure.sh` - **All-in-one infrastructure setup**:
     - Creates VPC, Subnets, Security Groups
     - Creates Application Load Balancer (ALB) with path-based routing
     - Creates S3 buckets (data + CloudWatch export)
     - Creates Service Discovery namespace
     - Sets up IAM roles
   - `register-task-definitions.sh` - Register task definitions with ECS (automatically sets ALB DNS)
   - `create-services.sh` - Create ECS services (automatically registers with ALB)
   - `add-monitoring.sh` - Deploy Prometheus + Grafana (optional, included by default)
   - `sync-api-cors.sh` - Sync API CORS with frontend IP (still needed)
   - `setup-autoscaling.sh` - Configure auto-scaling for ECS services
   - `get-service-ips.sh` - Get ALB DNS name and service IPs
   - `force-redeploy-service.sh` - Force redeploy a service (useful after IAM changes)
   - `check-service-status.sh` - Diagnose service issues
   - `diagnose-frontend.sh` - Troubleshoot frontend health issues
   - `fix-frontend-health.sh` - Quick fix for frontend health checks
   - `cleanup-infrastructure.sh` - Remove all infrastructure

   **Key Features**:
   - ✅ **ALB automatically created** - Single entry point with stable DNS
   - ✅ **Path-based routing** - `/` → Frontend, `/api/*` → API
   - ✅ **S3 buckets automatically created** - No separate script needed
   - ✅ **Monitoring included by default** - Can skip with `SKIP_MONITORING=true`

3. **Monitoring** (`deployment/aws/grafana/`)
   - `dashboards/rag-metrics.json` - Pre-configured Grafana dashboard for RAG metrics
   - `README.md` - Grafana setup instructions

4. **Configuration**
   - `deployment/aws/prometheus/prometheus.yml` - Prometheus config for ECS
   - `deployment/aws/README.md` - Complete AWS deployment guide

5. **Documentation**
   - `docs/CI_CD/07_PHASE4_ECS_DEPLOYMENT.md` - Step-by-step Phase 4 guide
   - `aws/IAM_PERMISSIONS_REQUIRED.md` - Complete IAM permissions guide for CI/CD

6. **GitHub Actions**
   - Updated `.github/workflows/test.yml` with Phase 4 deployment jobs

## 🚀 What You Need to Do

### Step 0: Set Up IAM User Permissions for CI/CD ⚠️ **IMPORTANT**

**Before you start**, your IAM user (`github-actions-ci-cd`) needs permission to register task definitions. This is required for the CI/CD pipeline to work.

#### Why This Is Needed

When GitHub Actions tries to register task definitions (Phase 3), it needs the `iam:PassRole` permission to tell ECS "use this role when running tasks". Without this, you'll get an `AccessDeniedException`.

#### The Fix: Add PassRole Permission
Here's a complete policy that includes all necessary permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ECSTaskDefinitionPassRole",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::YOUR_ACCOUNT_ID:role/ecsTaskExecutionRole"
    },
    {
      "Sid": "ECSFullAccess",
      "Effect": "Allow",
      "Action": [
        "ecs:*",
        "ecr:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ServiceDiscovery",
      "Effect": "Allow",
      "Action": [
        "servicediscovery:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "EC2Network",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeVpcs",
        "ec2:DescribeSubnets",
        "ec2:DescribeSecurityGroups",
        "ec2:CreateSecurityGroup",
        "ec2:AuthorizeSecurityGroupIngress",
        "ec2:RevokeSecurityGroupIngress",
        "ec2:DeleteSecurityGroup"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:DescribeLogGroups",
        "logs:DeleteLogGroup"
      ],
      "Resource": "*"
    },
    {
      "Sid": "SecretsManager",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": "arn:aws:secretsmanager:*:YOUR_ACCOUNT_ID:secret:esa-iagen/*"
    }
  ]
}
```

## How to Add Permissions: Via AWS Console

1. Go to **IAM Console** → **Users** → `github-actions-ci-cd`
2. Click **Add permissions** → **Attach policies directly**
3. Click **Create policy**
4. Switch to **JSON** tab
5. Paste the policy above (replace `YOUR_ACCOUNT_ID` with your account ID)
6. Click **Next** → Name it `ESAIAGenCICDPolicy`
7. Click **Create policy**
8. Go back to the user and attach the new policy

- **Step 2.5** = Permission for the **ECS role** (`ecsTaskExecutionRole`) to read secrets

### Step 1: Set Up AWS Infrastructure (One-Time)

```bash
cd deployment/aws/scripts
./setup-infrastructure.sh
```

This creates:
- ECS Cluster
- VPC, Subnets, Security Groups
- Service Discovery Namespace
- IAM Roles
- **Application Load Balancer (ALB)** with path-based routing:
  - `http://<ALB_DNS>/` → Frontend
  - `http://<ALB_DNS>/api/*` → API
- **S3 Buckets** (automatically created):
  - `esa-iagen-data` (main data bucket)
  - `esa-iagen-cloudwatch` (CloudWatch exports)

**Time**: ~5-10 minutes

**Note**: The ALB DNS name is saved to `infrastructure-ids.txt` and will be automatically used by the frontend.

### Step 2: Set Up AWS Secrets Manager

Store your API keys securely:

```bash
# Get your region from infrastructure-ids.txt after Step 1
source aws/infrastructure-ids.txt

# Store Anthropic API key
aws secretsmanager create-secret \
  --name esa-iagen/ANTHROPIC_API_KEY \
  --secret-string "your-anthropic-api-key" \
  --region $AWS_REGION

# Store OpenAI API key (optional)
aws secretsmanager create-secret \
  --name esa-iagen/OPENAI_API_KEY \
  --secret-string "your-openai-api-key" \
  --region $AWS_REGION
```

**Note**: If you prefer environment variables instead of Secrets Manager, you can modify `task-api.json` to use `environment` instead of `secrets`.

### Step 2.5: Add IAM Policy for Secrets Manager Access ⚠️ **IMPORTANT**

**This is a critical step!** Without this, your API service will fail to start with an `AccessDeniedException`.

#### Why This Is Needed

This is a classic "Day 2" ECS error. You are getting it because the standard `AmazonECSTaskExecutionRolePolicy` (which you likely attached in the previous step) only gives permission for **ECR** (images) and **CloudWatch** (logs). It does *not* include permission to read **Secrets Manager** by default.

Think of it this way: You gave the "Waiter" (ECS Agent) permission to enter the kitchen (ECR), but you didn't give them the key to the safe (Secrets Manager) where the API keys are kept.

#### The Fix: Add an Inline Policy

You need to manually grant your `ecsTaskExecutionRole` permission to read that specific secret.

1. **Log in to the AWS Console** and go to **IAM**.
2. Click **Roles** on the left and search for **`ecsTaskExecutionRole`**.
3. Click on the role name to open it.
4. On the **Permissions** tab, click **Add permissions** → **Create inline policy**.
5. Click the **JSON** tab and paste this policy (it allows reading *only* your specific key):

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "secretsmanager:GetSecretValue",
                "kms:Decrypt"
            ],
            "Resource": [
                "arn:aws:secretsmanager:eu-north-1:YOUR_ACCOUNT_ID:secret:esa-iagen/ANTHROPIC_API_KEY-*",
                "arn:aws:secretsmanager:eu-north-1:YOUR_ACCOUNT_ID:secret:esa-iagen/OPENAI_API_KEY-*",
                "arn:aws:secretsmanager:eu-north-1:YOUR_ACCOUNT_ID:secret:GRAFANA_ADMIN_PASSWORD-*"
            ]
        }
    ]
}
```

**Important Notes:**
- Replace `YOUR_ACCOUNT_ID` with your actual AWS Account ID (found in `aws/infrastructure-ids.txt` or in the top right corner of the console).
  - **Example**: If your account ID is `790402872278`, use `arn:aws:secretsmanager:eu-north-1:790402872278:secret:...`
- Replace `eu-north-1` with your region if different.
- **Note on the `*`:** Secrets Manager adds 6 random characters to the end of ARNs (e.g., `-AbCdE`). Adding `-*` ensures the policy works even if that suffix changes.
- The policy includes:
  - `ANTHROPIC_API_KEY` (required for API service)
  - `OPENAI_API_KEY` (optional, remove if not used)
  - `GRAFANA_ADMIN_PASSWORD` (required if using Grafana monitoring)
- **Common mistake**: Don't use double colons (`::`) - always include the account ID: `:YOUR_ACCOUNT_ID:`

6. Click **Next**.
7. Name the policy: **`ECSSecretsAccess`**.
8. Click **Create policy**.

#### Why `kms:Decrypt`?

I included `kms:Decrypt` in the policy above just in case your secret is encrypted with a custom KMS key. If you are using the default key, you strictly only need `secretsmanager:GetSecretValue`, but adding `kms:Decrypt` often prevents a second "Access Denied" error immediately following this one.

Once you add this policy, you need to **force a new deployment** so ECS tries to start the task again with the new permissions.

### Step 3: Register Task Definitions

```bash
cd aws/scripts
./register-task-definitions.sh
```

This registers task definitions with ECS:
- **Essential**: Qdrant, API, Frontend
- **Monitoring** (included by default): Prometheus, Grafana

**What happens automatically:**
- Frontend task definition is updated with ALB DNS name (`NEXT_PUBLIC_API_URL`)
- All placeholders are replaced with your AWS account ID and region

**To skip monitoring**: `SKIP_MONITORING=true ./register-task-definitions.sh`

**Time**: ~2 minutes

**Note**: These will be deleted by `cleanup-infrastructure.sh` (deregistered)

### Step 4: Create ECS Services

```bash
cd aws/scripts
./create-services.sh
```

This creates ECS services for all containers:
- **Essential**: Qdrant, API, Frontend
- **Monitoring** (included by default): Prometheus, Grafana

**ALB Integration:**
- API service is automatically registered with ALB target group
- Frontend service is automatically registered with ALB target group
- Both services are accessible via ALB DNS name (stable, never changes)

**To skip monitoring**: `SKIP_MONITORING=true ./create-services.sh`

**Time**: ~5 minutes

**Note**: These will be deleted by `cleanup-infrastructure.sh`

### Step 5: Access Your Application (ALB DNS Name)

**✅ No manual steps required!** The ALB DNS name is automatically configured.

**Access your application:**
- **Frontend**: `http://<ALB_DNS_NAME>/`
- **API**: `http://<ALB_DNS_NAME>/api/*`
- **Swagger UI**: `http://<ALB_DNS_NAME>/docs` (Interactive API documentation)
- **ReDoc**: `http://<ALB_DNS_NAME>/redoc` (Alternative API documentation)
- **Health Check**: `http://<ALB_DNS_NAME>/health`
- **Metrics**: `http://<ALB_DNS_NAME>/metrics` (Prometheus metrics)

**Get your ALB DNS name:**
```bash
cd aws/scripts
source ../infrastructure-ids.txt
echo "Frontend: http://$ALB_DNS_NAME/"
echo "API Docs: http://$ALB_DNS_NAME/docs"
echo "API: http://$ALB_DNS_NAME/api/health"
```

**Or use the helper script if it does not work:**
```bash
cd aws/scripts
./get-service-ips.sh
```

**Key benefits of ALB:**
- ✅ Stable DNS name (never changes, even if services restart)
- ✅ Path-based routing (`/` → Frontend, `/api/*` → API, `/docs` → API)
- ✅ Automatic health checks and failover
- ✅ Single entry point for all traffic

**Note**: The ALB routes for `/docs`, `/redoc`, `/health`, and `/metrics` are automatically added by `setup-infrastructure.sh`. If you have an existing ALB that doesn't have these routes, run:
```bash
cd aws/scripts
./add-api-docs-routes.sh
```

This adds ALB rules for:
- `/docs` → API (Swagger UI)
- `/redoc` → API (ReDoc documentation)
- `/openapi.json` → API (OpenAPI schema)
- `/health` → API (health checks)
- `/metrics` → API (Prometheus metrics)

### Step 6: Sync API CORS with Frontend IP (After Services Start)

**⚠️ Yes, this is still required even with ALB!**

**Why?** ALB solves where requests go TO (stable API URL), but CORS checks where requests come FROM (frontend origin).

- **ALB solves**: Frontend → API URL (stable DNS name)
- **CORS checks**: Browser sends `Origin: http://13.53.39.202:3000` header
- **Problem**: Frontend's public IP changes on restart → CORS blocks if not in allowlist

After services are running, sync CORS to allow requests from the current frontend IP:

```bash
cd aws/scripts
./sync-api-cors.sh
```

**What this does:**
- Gets current frontend service public IP
- Updates API task definition CORS origins to include it
- Registers and redeploys API service

**After adding the policy**, force redeploy API service:
```bash
./force-redeploy-service.sh esa-iagen-api-service
```

**When to run `sync-api-cors.sh`:**

| Event | Frontend IP Changes? | Need CORS Sync? |
|-------|---------------------|-----------------|
| ✅ **Frontend service redeploys** | ✅ Yes | ✅ **YES** - Run it |
| ✅ **After initial infrastructure setup** | ✅ Yes | ✅ **YES** - Run it |
| ✅ **If you see CORS errors** | ✅ Likely | ✅ **YES** - Run it |
| ❌ **API service redeploys** | ❌ No | ❌ **NO** - Not needed |
| ❌ **Qdrant service redeploys** | ❌ No | ❌ **NO** - Not needed |
| ❌ **Code push (no service restart)** | ❌ No | ❌ **NO** - Not needed |

**TL;DR**: Only run it when the frontend service restarts and gets a new IP.

**Time**: ~1-2 minutes

**Note**: This ensures CORS allows requests from the current frontend IP. Without this, browser will block requests if frontend IP changes.

**Quick check**: If unsure, check if frontend IP changed:
```bash
cd aws/scripts
./get-service-ips.sh
```
Compare the frontend IP with the current CORS config. If different, run `sync-api-cors.sh`.

**Automation option**: You can automate this in CI/CD by adding this to your GitHub Actions workflow after frontend deployment:
```yaml
- name: Sync API CORS with Frontend IP
  run: |
    cd aws/scripts
    ./sync-api-cors.sh
```

**Future solution**: Put frontend behind ALB too → stable DNS → CORS never needs updating


### Step 7: S3 Buckets (Already Created)

**✅ S3 buckets are automatically created** by `setup-infrastructure.sh` (Step 1). No separate script needed!

**What was created:**
- Main data bucket (`esa-iagen-data`) with lifecycle policies
- CloudWatch export bucket (`esa-iagen-cloudwatch`)
- Folder structure (query-history/, metrics/, logs/, backups/)
- Encryption and versioning enabled

**Time**: 0 minutes (already done!) ✅

### Step 7.5: Update IAM Permissions for S3

**Manual Steps** (requires admin access):
1. Go to AWS Console → IAM → Roles → `ecsTaskExecutionRole`
2. Add permissions → Create inline policy
3. Use JSON tab and paste the policy below (or from the generated file)
4. Name it: `ESAIAGenS3CloudWatchPolicy`
5. Create policy

**IAM Policy JSON** (copy and paste this):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::esa-iagen-data",
        "arn:aws:s3:::esa-iagen-data/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "cloudwatch:PutMetricData",
        "cloudwatch:GetMetricStatistics",
        "cloudwatch:ListMetrics"
      ],
      "Resource": "*"
    }
  ]
}
```

**After adding the policy**, force redeploy API service:
```bash
./force-redeploy-service.sh esa-iagen-grafana-service
```

**Time**: ~2-3 minutes (manual setup)

### Step 7.7: Set Up Auto-Scaling (Optional but Recommended)

**Why**: Automatically scale API service based on load.

```bash
cd aws/scripts
./setup-autoscaling.sh
```

This configures:
- Auto-scaling for API service (1-5 tasks)
- CPU-based scaling (target: 70%)
- Memory-based scaling (target: 80%)

**Time**: ~1 minute

### Step 8: Verify Services Are Running

```bash
# Check service status
aws ecs list-services --cluster esa-iagen-cluster --region YOUR_REGION

# View running tasks
aws ecs list-tasks --cluster esa-iagen-cluster --region YOUR_REGION

# Get service IPs
cd aws/scripts
./get-service-ips.sh

# Check logs
aws logs tail /ecs/esa-iagen --follow --region YOUR_REGION
```

### Step 9: Test Deployment

Push to `main` branch to trigger automatic deployment:

```bash
git add .
git commit -m "Add Phase 4: ECS deployment"
git push origin main
```

GitHub Actions will:
1. ✅ Run tests (Phase 1)
2. ✅ Build images (Phase 2)
3. ✅ Push to ECR (Phase 3)
4. 🚀 **Deploy to ECS (Phase 4)** ← NEW!


## 📊 Step 10: Configure Monitoring (Prometheus + Grafana)

**Note**: Monitoring is **deployed automatically** with `create-services.sh` (Step 4). This step is for **configuration only**.

If you skipped monitoring (`SKIP_MONITORING=true`), you can add it later:
```bash
cd aws/scripts
./add-monitoring.sh
```

### What Gets Created

| Service | Port | URL | Credentials |
|---------|------|-----|-------------|
| Prometheus | 9090 | `http://<prometheus-ip>:9090` | None |
| Grafana | 3002 | `http://<grafana-ip>:3002` | admin / admin |

### After Deployment: Configure Grafana + Prometheus

#### 1️⃣ Get Monitoring IPs

```bash
cd aws/scripts
./get-service-ips.sh
```

You'll see:
```
📊 Monitoring Services:
📡 esa-iagen-prometheus-service:
   ✅ Public IP: X.X.X.X
   🔗 URL: http://X.X.X.X:9090
📡 esa-iagen-grafana-service:
   ✅ Public IP: Y.Y.Y.Y
   🔗 URL: http://Y.Y.Y.Y:3002
```

#### 2️⃣ Access Grafana

| URL | Credentials |
|-----|-------------|
| `http://<grafana-ip>:3002` | admin / admin |

(Te pedirá cambiar password en primer login)

#### 3️⃣ Add Prometheus as Data Source

1. Go to **⚙️ Configuration** → **Data Sources**
2. Click **Add data source**
3. Select **Prometheus**
4. In **URL** enter: `http://prometheus.esa-iagen.local:9090`
5. Click **Save & Test** → Should show ✅ "Data source is working"

#### 4️⃣ Import RAG Dashboard

1. Go to **➕** → **Import**
2. Click **Upload JSON file**
3. Select: `aws/grafana/dashboards/rag-metrics.json`
4. Select Prometheus data source
5. Click **Import**

#### 5️⃣ Verify Prometheus Scraping

1. Open Prometheus: `http://<prometheus-ip>:9090`
2. Go to **Status** → **Targets**
3. You should see `sentiwiki-rag-api` with status **UP** ✅

If target is **DOWN**:
- Make a query first: `curl http://<api-ip>:8000/health`
- Check API service is running
- Security group allows port 8000 internally

### Metrics Tracked Automatically

Every query to your API automatically registers:

| Metric | What it measures |
|--------|------------------|
| `rag_queries_total` | Total RAG queries |
| `rag_query_duration_seconds` | End-to-end latency |
| `rag_retrieval_duration_seconds` | Retrieval time |
| `rag_llm_duration_seconds` | LLM generation time |
| `llm_tokens_total` | Tokens used (prompt/completion) |
| `llm_cost_total` | Cost in USD per model |
| `agent_routing_decisions_total` | RAG vs Direct routing |

### Cost Impact

| Service | Monthly Cost |
|---------|--------------|
| Prometheus | ~$3/month |
| Grafana | ~$3/month |
| **Total Additional** | **~$6/month** |

**Note**: Data is stored in memory (not persistent). Prometheus retains 30 days of data, but data is lost if the container restarts. For persistent storage, you'd need EFS (~$10-15/month additional).

### Verify Prometheus is Scraping

After deployment, check Prometheus targets:
1. Open `http://<prometheus-ip>:9090/targets`
2. You should see `sentiwiki-rag-api` target as **UP**

If target is **DOWN**, check:
- API service is running
- Security group allows internal traffic (port 8000)
- Service Discovery is working (`api.esa-iagen.local` resolves)

---






## 📋 Important Notes

### Service Discovery (Service-to-Service Communication)

**Yes, services can still talk to each other!** ✅

**Service-to-service communication** uses **Service Discovery** (internal DNS names).

**How services communicate:**
- **Browser → ALB**: `http://<ALB_DNS>/` (Frontend) or `http://<ALB_DNS>/api/*` (API)
- **ALB → Services**: Routes traffic to Frontend (port 3000) or API (port 8000) based on path
- **API → Qdrant**: `qdrant.esa-iagen.local:6333` (Service Discovery - internal)
- **Prometheus → API**: `api.esa-iagen.local:8000` (Service Discovery - internal)

**Key Points:**
- ✅ **ALB provides stable DNS** - Single entry point that never changes
- ✅ **Path-based routing** - `/` → Frontend, `/api/*` → API
- ✅ **Service Discovery works inside VPC** - Services can always find each other via `.esa-iagen.local` DNS names
- ✅ **Internal communication is automatic** - API connects to Qdrant via Service Discovery
- ✅ **External access uses ALB** - Browser → ALB → Services (stable DNS, no IP changes)

**Example Flow:**
1. **Browser** → `http://<ALB_DNS>/` → **ALB** → **Frontend** (port 3000)
2. **Frontend** → `http://<ALB_DNS>/api/query` → **ALB** → **API** (port 8000)
3. **API** → `qdrant.esa-iagen.local:6333` → **Qdrant** (internal, Service Discovery)

All of this works automatically - no additional configuration needed!

### Storage

**Note**: Data is stored ephemerally (in container filesystem). Data will be lost when containers restart. For production, consider using EFS or S3 for persistent storage if needed.

### Public Images

Qdrant uses a public Docker Hub image, so it doesn't need to be pushed to ECR. Only API and Frontend are built and pushed.

**Note**: Prometheus and Grafana are **deployed by default** with `create-services.sh`. To skip monitoring, use `SKIP_MONITORING=true ./create-services.sh`.



## 🔧 Troubleshooting

### API Service Won't Start - "AccessDeniedException" for Secrets Manager

**Symptom**: Service shows "No running tasks" and stopped tasks show:
```
AccessDeniedException: User: arn:aws:sts::...:assumed-role/ecsTaskExecutionRole/... 
is not authorized to perform: secretsmanager:GetSecretValue
```

**Solution**: This means the `ecsTaskExecutionRole` doesn't have permission to read secrets. 

**Fix**: Follow **Step 2.5** above to add the IAM inline policy for Secrets Manager access. This is a required step that many people miss!

**Common mistakes in the policy:**
- ❌ Missing account ID: `arn:aws:secretsmanager:eu-north-1::secret:...` (double colon)
- ✅ Correct format: `arn:aws:secretsmanager:eu-north-1:790402872278:secret:...` (with account ID)
- ❌ Missing `-*` suffix: `secret:GRAFANA_ADMIN_PASSWORD` (won't work if secret has suffix)
- ✅ Correct format: `secret:GRAFANA_ADMIN_PASSWORD-*` (with wildcard)

**After adding the policy**, you must force a new deployment:

```bash
# Quick way: Use the helper script
cd aws/scripts
./force-redeploy-service.sh esa-iagen-api-service

# Or manually:
source aws/infrastructure-ids.txt
aws ecs update-service \
  --cluster esa-iagen-cluster \
  --service esa-iagen-api-service \
  --force-new-deployment \
  --region $AWS_REGION
```

**Diagnostic tool**: Run `./check-service-status.sh` to see detailed error messages.

### Grafana Service Won't Start - "AccessDeniedException" for GRAFANA_ADMIN_PASSWORD

**Symptom**: Grafana service shows "No running tasks" and stopped tasks show:
```
AccessDeniedException: User: arn:aws:sts::...:assumed-role/ecsTaskExecutionRole/... 
is not authorized to perform: secretsmanager:GetSecretValue on resource: 
arn:aws:secretsmanager:eu-north-1:790402872278:secret:GRAFANA_ADMIN_PASSWORD
```

**Solution**: The IAM policy is missing the `GRAFANA_ADMIN_PASSWORD` secret, or the ARN format is incorrect.

**Fix**: Update the IAM inline policy for `ecsTaskExecutionRole` to include the Grafana secret:

1. Go to **IAM Console** → **Roles** → `ecsTaskExecutionRole`
2. Click **Permissions** → Find the inline policy (e.g., `ECSSecretsAccess`)
3. Click **Edit** → **JSON** tab
4. Add the Grafana secret to the Resource array:
   ```json
   "Resource": [
       "arn:aws:secretsmanager:eu-north-1:YOUR_ACCOUNT_ID:secret:esa-iagen/ANTHROPIC_API_KEY-*",
       "arn:aws:secretsmanager:eu-north-1:YOUR_ACCOUNT_ID:secret:esa-iagen/OPENAI_API_KEY-*",
       "arn:aws:secretsmanager:eu-north-1:YOUR_ACCOUNT_ID:secret:GRAFANA_ADMIN_PASSWORD-*"
   ]
   ```
5. **Important**: Replace `YOUR_ACCOUNT_ID` with your actual account ID (e.g., `790402872278`)
6. Save the policy

**After updating the policy**, force a new deployment:

```bash
cd aws/scripts
./force-redeploy-service.sh esa-iagen-grafana-service
```

**Note**: If you haven't created the `GRAFANA_ADMIN_PASSWORD` secret yet, run:
```bash
cd aws/scripts
./setup-grafana-secret.sh
```

### Task Definition Registration Fails - "AccessDeniedException" for PassRole

**Symptom**: When running `register-task-definitions.sh`, you get:
```
AccessDeniedException: User: arn:aws:iam::...:user/github-actions-ci-cd 
is not authorized to perform: iam:PassRole
```

**Solution**: Your IAM user (`github-actions-ci-cd`) needs the `iam:PassRole` permission.

**Fix**: Follow **Step 0** above to add the IAM inline policy for PassRole. This is required for the CI/CD pipeline to register task definitions.

**More details**: See `aws/IAM_PERMISSIONS_REQUIRED.md` for complete IAM policy options and troubleshooting.

### Container Killed - "OutOfMemoryError" (Exit Code 137)

**Symptom**: Service shows tasks stopping with:
```
Exit code: 137, reason: "OutOfMemoryError: Container killed due to memory usage"
```

**Solution**: The container doesn't have enough memory. The API loads ML models that need ~1.7GB per worker.

**Fix**: Increase memory allocation in the task definition:

1. **Edit `aws/task-definitions/task-api.json`**:
   ```json
   {
     "cpu": "1024",
     "memory": "2048"
   }
   ```

2. **Re-register the task definition**:
   ```bash
   cd aws/scripts
   ./register-task-definitions.sh
   ```

3. **Force a new deployment**:
   ```bash
   ./force-redeploy-service.sh esa-iagen-api-service
   ```

**Why this happens**:
- The API loads two large ML models: embedding model (~1.3GB) + reranker (~420MB) = ~1.7GB
- Plus Python, FastAPI, and other dependencies = ~2GB total
- The default 512MB is too small

**Memory recommendations**:
- **Minimum**: 2048 MB (2 GB) for 1 worker
- **Recommended**: 3072 MB (3 GB) for safety margin
- **Production**: 4096 MB (4 GB) if using multiple workers

**Note**: Fargate CPU/memory combinations must match. Valid pairs:
- 1024 CPU (1 vCPU) → 2048-4096 MB
- 2048 CPU (2 vCPU) → 4096-8192 MB

### Services Won't Start

```bash
# Check service events
aws ecs describe-services \
  --cluster esa-iagen-cluster \
  --services esa-iagen-api-service \
  --region YOUR_REGION \
  --query 'services[0].events[:5]'
```

### Container Keeps Restarting

```bash
# Check logs
aws logs tail /ecs/esa-iagen --follow --region YOUR_REGION
```

### Tasks Can't Reach ECR, CloudWatch, or Secrets Manager

**Symptom**: Tasks fail with errors like:
```
ResourceInitializationError: unable to pull secrets or registry auth
The task cannot pull registry auth from Amazon ECR
There is a connection issue between the task and Amazon CloudWatch
```

**Solution**: Your subnets are **private** (no internet access). Tasks need internet to:
- Pull images from ECR
- Send logs to CloudWatch
- Read secrets from Secrets Manager

**Fix (FREE option - recommended)**:
```bash
cd aws/scripts
./make-subnets-public.sh
```

This associates your subnets with a route table that has a route to the Internet Gateway. **This is FREE** (no NAT Gateway needed).

**Alternative (expensive)**: Use NAT Gateway (~$32/month) for private subnets (more secure but costly).

**After fixing**, redeploy services:
```bash
./force-redeploy-service.sh esa-iagen-api-service
./force-redeploy-service.sh esa-iagen-qdrant-service
./force-redeploy-service.sh esa-iagen-frontend-service
```

**Verify subnets are public**:
```bash
./check-subnet-public.sh
```

### Services Can't Find Each Other (API ↔ Qdrant Communication)

**Important**: Service-to-service communication uses Service Discovery (internal DNS).

**Common causes:**
1. Service Discovery not set up
2. Security group blocking internal traffic
3. Services not registered with Service Discovery

**Quick fix** (most common issue):
```bash
source aws/infrastructure-ids.txt

# Add rule to allow internal traffic (service-to-service)
aws ec2 authorize-security-group-ingress \
  --group-id $SECURITY_GROUP_ID \
  --protocol -1 \
  --source-group $SECURITY_GROUP_ID \
  --region $AWS_REGION

# Redeploy services
cd aws/scripts
./force-redeploy-service.sh esa-iagen-api-service
./force-redeploy-service.sh esa-iagen-qdrant-service
```

**Full troubleshooting**: See [Service-to-Service Communication Guide](SERVICE_TO_SERVICE_COMMUNICATION.md) for complete diagnostic steps.

### Frontend Can't Connect to API - Wrong API URL

**Symptom**: Frontend shows error: "Cannot connect to API at http://localhost:8002"

**Cause**: Frontend Docker image was built before ALB existed, so it has `localhost:8002` hardcoded in the JavaScript bundle.

**Why this happens**: Next.js injects `NEXT_PUBLIC_*` environment variables at **BUILD TIME** into the client-side bundle. Even though the task definition has the ALB URL, the JavaScript bundle was already compiled with `localhost:8002`.

**Fix**: Rebuild the frontend image with the ALB DNS name:
1. Get ALB DNS name from `infrastructure-ids.txt`
2. Rebuild frontend image with `NEXT_PUBLIC_API_URL=http://<ALB_DNS>` build arg
3. Push to ECR and redeploy

**Prevention**: The CI/CD workflow (`.github/workflows/test.yml`) should already handle this by:
1. Getting ALB DNS name from AWS
2. Passing it as `NEXT_PUBLIC_API_URL` build arg during Docker build

**More details**: See `aws/scripts/ALB_CONNECTION_DIAGNOSTIC_RESULTS.md` for complete troubleshooting guide.

### Can't Access /docs or Other API Endpoints

**Symptom**: Accessing `http://<ALB_DNS>/docs` returns 404 or routes to Frontend instead of API.

**Cause**: The ALB doesn't have routing rules for FastAPI documentation endpoints (`/docs`, `/redoc`, `/health`, `/metrics`).

**Why this happens**: If you created the ALB before the infrastructure script was updated, or if the routes weren't added automatically, these endpoints won't be configured.

**Fix**: Add the missing ALB rules:

```bash
cd aws/scripts
./add-api-docs-routes.sh
```

This script adds ALB rules for:
- `/docs` → API (Swagger UI)
- `/redoc` → API (ReDoc documentation)
- `/openapi.json` → API (OpenAPI schema)
- `/health` → API (health checks)
- `/metrics` → API (Prometheus metrics)

**After running the script**, test the endpoints:
```bash
# Get your ALB DNS name
source ../infrastructure-ids.txt

# Test Swagger UI
curl -I http://$ALB_DNS_NAME/docs

# Test health check
curl http://$ALB_DNS_NAME/health
```

**Note**: The `setup-infrastructure.sh` script (Step 1) now automatically adds these routes. If you're setting up fresh infrastructure, you don't need to run `add-api-docs-routes.sh` separately. However, if you have an existing ALB that was created before this update, you'll need to run the script to add the missing routes.

## 📚 Next Steps

After Phase 4 is working:

1. **Add Monitoring** - Monitoring is included by default! (see Step 10 above)
2. **S3 Storage** - Already created automatically! ✅ (see Step 7 above)
3. **Set up Auto Scaling** - Run `./setup-autoscaling.sh` (see Step 7.7 above)
4. **Add CloudWatch Alarms** - Run `./setup-cloudwatch-advanced.sh` (see Step 7.6 above)
5. **Application Load Balancer** - Already integrated! ✅ (see Step 1 and Step 5 above)
   - Static DNS name (no IP updates needed)
   - Path-based routing (`/` → Frontend, `/api/*` → API)
   - Health checks and failover
   - SSL/TLS termination (can be added)
6. **Use Custom Domain** - Point your domain to Load Balancer
7. **Set up Staging Environment** - Deploy `develop` branch to staging
8. **Enable S3 Query Logging** - Configure API to log queries to S3 (see below)

### Enable S3 Query Logging

To enable automatic logging of RAG queries/responses to S3:

1. **Set environment variable in task definition** (`task-api.json`):
   ```json
   {
     "environment": [
       {
         "name": "S3_BUCKET_NAME",
         "value": "esa-iagen-data"
       },
       {
         "name": "S3_LOGGING_ENABLED",
         "value": "true"
       }
     ]
   }
   ```

2. **Re-register and redeploy**:
   ```bash
   cd aws/scripts
   ./register-task-definitions.sh
   ./force-redeploy-service.sh esa-iagen-api-service
   ```

3. **Verify logging**: Check S3 bucket after making a query:
   ```bash
   aws s3 ls s3://esa-iagen-data/query-history/ --recursive
   ```

**What gets logged**:
- Query text and timestamp
- Route decision (RAG vs DIRECT)
- Response (answer, sources, context)
- Metadata (duration, tokens, cost)
- Agent state (rewritten queries, grade scores)

## 🔄 Managing Application Access (ALB)

### ALB DNS Name (Automatic)

**How it works:**
- ALB is created automatically during `setup-infrastructure.sh` (Step 1)
- ALB DNS name is saved to `infrastructure-ids.txt`
- Frontend task definition is automatically updated with ALB DNS during `register-task-definitions.sh`
- DNS name never changes (even if services restart)

**Access your application:**
```bash
cd aws/scripts
source ../infrastructure-ids.txt
echo "Frontend: http://$ALB_DNS_NAME/"
echo "API: http://$ALB_DNS_NAME/api/health"
```

**Path-based routing:**
- `http://<ALB_DNS>/` → Frontend (port 3000)
- `http://<ALB_DNS>/docs` → API (Swagger UI)
- `http://<ALB_DNS>/redoc` → API (ReDoc)
- `http://<ALB_DNS>/health` → API (health check)
- `http://<ALB_DNS>/metrics` → API (Prometheus metrics)
- `http://<ALB_DNS>/api/*` → API (all API endpoints)

**What to do if frontend can't connect:**
1. Verify ALB DNS name is correct in `infrastructure-ids.txt`
2. Re-register task definitions: `./register-task-definitions.sh`
3. Force frontend redeploy: `./force-redeploy-service.sh esa-iagen-frontend-service`

**ALB Features:**
- ✅ Stable DNS name (never changes)
- ✅ Path-based routing
- ✅ Automatic health checks and failover
- ✅ Single entry point for all traffic
- ✅ Cost: ~$16/month

**Note**: If the frontend Docker image was built before ALB existed, you may need to rebuild it with the ALB DNS name. See troubleshooting section above.

## 💰 Cost Estimate

- **Free Tier**: First 12 months (most services free)
- **After Free Tier**: ~$9-12/month for 3 essential services
- **With Monitoring** (included by default): +$6/month (Prometheus + Grafana) = ~$15-18/month total
- **With ALB**: +$16/month (Application Load Balancer) = ~$25-34/month total
- **With S3**: +$0.023/GB/month (Standard storage, first 5GB free)
- **With CloudWatch Advanced**: +$0 (dashboards and alarms are free, only pay for custom metrics)
- **With Auto-Scaling**: +$0 (only pay for additional tasks when scaling up)

**Total with all features** (including ALB): ~$25-34/month (depending on S3 usage and auto-scaling)

**S3 Storage Costs** (typical usage):
- Query history: ~100MB/month = $0.002/month
- Metrics exports: ~50MB/month = $0.001/month
- **Total S3**: ~$0.01-0.05/month (very low)

See `07_PHASE4_ECS_DEPLOYMENT.md` for detailed cost breakdown.

## 🧹 Cleanup (Remove All Infrastructure)

When you're done testing or want to avoid ongoing costs:

```bash
cd aws/scripts
./cleanup-infrastructure.sh
```

This will delete **everything** created by the setup scripts:
- ✅ **ECS Services** (from Step 4: Qdrant, API, Frontend services)
- ✅ **Task Definitions** (from Step 3: All registered task definitions)
- ✅ **Service Discovery** (services and namespace)
- ✅ **Security Groups** (ECS security group and all rules)
- ✅ **CloudWatch Logs** (log group)
- ✅ **ECS Cluster**

**What it does NOT delete:**
- ⚠️ **ECR repositories and images** (you may want to keep these)
- ⚠️ **IAM roles** (may be used by other resources)
- ⚠️ **Network resources** (persistent, account-level):
  - **VPC** (default VPC)
  - **Subnets**
  - **Route Tables and associations** (subnets remain public)
  - **Internet Gateway**

**Important**: Network changes (like making subnets public) **persist** across cleanup/setup cycles. Once you run `make-subnets-public.sh`, the subnets will remain public even after cleanup. When you run `setup-infrastructure.sh` again, it will detect and use the public subnets automatically.

**Network Resources Cost**: **$0/month** ✅
- VPC: Free
- Subnets: Free
- Route Tables: Free
- Internet Gateway: Free
- Route table associations: Free

These are all free AWS resources. Only data transfer costs money (but minimal for small projects).

### 📝 About Network Scripts (`make-subnets-public.sh`, `check-subnet-public.sh`)

**Why keep these scripts if network changes persist?**

Once subnets are made public, they **stay public forever** (until manually changed). So why keep these scripts?

**They're useful for:**
1. **First-time setup** - New AWS accounts/regions may have private subnets
2. **Troubleshooting** - Verify subnet configuration when tasks can't reach AWS services
3. **Manual fixes** - If `setup-infrastructure.sh` fails to make subnets public automatically
4. **Different VPCs** - If you switch to a custom VPC, you may need to make its subnets public

**Note**: `setup-infrastructure.sh` now **automatically makes subnets public** if needed, so you rarely need to run these scripts manually. They're mainly for troubleshooting and edge cases.

**After first run**: Once subnets are public in your account, you won't need these scripts again unless you switch accounts/regions or troubleshoot network issues.

## 💰 Cost Impact After Cleanup

After running `cleanup-infrastructure.sh`, **most costs are eliminated**:

### ✅ Costs Eliminated (No longer charged)
- **ECS Fargate**: $0/month (no running tasks)
- **ECS Cluster**: $0/month (cluster deleted)
- **Service Discovery**: $0/month (namespace deleted)
- **CloudWatch Logs**: $0/month (log group deleted)
- **Security Groups**: $0/month (free, but deleted anyway)

### ⚠️ Costs That May Remain
- **ECR Storage**: ~$0.10/GB/month (if you keep images)
  - Free tier: 500MB/month ✅
  - If you have < 500MB of images: **$0/month**
  - If you have > 500MB: Small storage cost
- **IAM Roles**: $0/month (always free, but not deleted)

### 🧹 To Eliminate ALL Costs

If you want to eliminate ECR costs too:

```bash
# Delete ECR repositories (this deletes all images too!)
aws ecr delete-repository --repository-name esa-iagen-api --force --region eu-north-1
aws ecr delete-repository --repository-name esa-iagen-frontend --force --region eu-north-1
```

**After cleanup + ECR deletion**: **$0/month** ✅

### 📊 Cost Summary

| Resource | Before Cleanup | After Cleanup | After ECR Deletion |
|----------|---------------|---------------|-------------------|
| ECS Fargate | ~$9-12/month | $0 | $0 |
| ECR Storage | ~$0-1/month | ~$0-1/month | $0 |
| **Total** | **~$9-13/month** | **~$0-1/month** | **$0** |

**Note**: ECR repositories and images are NOT deleted automatically. Delete them manually if needed:
```bash
aws ecr delete-repository --repository-name esa-iagen-api --force --region YOUR_REGION
aws ecr delete-repository --repository-name esa-iagen-frontend --force --region YOUR_REGION
```

## ✅ Checklist

- [ ] **Step 0**: Add IAM PassRole permission for `github-actions-ci-cd` user
- [ ] **Step 1**: Run `setup-infrastructure.sh` (creates ALB, S3 buckets automatically)
- [ ] **Step 2**: Set up AWS Secrets Manager for API keys
- [ ] **Step 2.5**: Add IAM Secrets Manager policy for `ecsTaskExecutionRole` role
- [ ] **Step 3**: Run `register-task-definitions.sh` (includes monitoring by default, sets ALB DNS)
- [ ] **Step 4**: Run `create-services.sh` (includes Prometheus + Grafana by default, registers with ALB)
- [ ] **Step 5**: Wait for services to start (~5 minutes), then get ALB DNS name
- [ ] **Step 6**: Run `sync-api-cors.sh` to sync API CORS with frontend IP
- [ ] **Step 7**: S3 buckets already created (automatic in Step 1) ✅
- [ ] **Step 7.5**: Add IAM S3/CloudWatch permissions for `ecsTaskExecutionRole` role
- [ ] **Step 7.7**: Set up auto-scaling (`./setup-autoscaling.sh`) - Optional but recommended
- [ ] **Step 8**: Verify services are running (`./get-service-ips.sh`)
- [ ] **Step 9**: Push to `main` to test automatic deployment
- [ ] **Step 10**: Configure Grafana (monitoring already deployed):
  - [ ] Open Grafana (`http://<grafana-ip>:3002`)
  - [ ] Add Prometheus data source (`http://prometheus.esa-iagen.local:9090`)
  - [ ] Import dashboard from `aws/grafana/dashboards/rag-metrics.json`
- [ ] Check logs to verify everything is working
- [ ] Access your application via ALB DNS name (`http://<ALB_DNS>/`)
- [ ] View CloudWatch dashboard (if Step 7.6 completed)
- [ ] Verify auto-scaling is working (if Step 7.7 completed)
- [ ] When done: Run `cleanup-infrastructure.sh` to remove resources

## 📝 Scripts: What to Keep vs Delete

### ✅ Essential Scripts (Keep)

- `setup-infrastructure.sh` - Infrastructure setup (creates ALB, S3 buckets, VPC, etc.)
- `register-task-definitions.sh` - Register task definitions (sets ALB DNS automatically)
- `create-services.sh` - Create ECS services (registers with ALB automatically)
- `add-monitoring.sh` - Deploy Prometheus + Grafana (optional, included by default)
- `add-api-docs-routes.sh` - Add ALB rules for FastAPI docs endpoints (`/docs`, `/redoc`, `/health`, `/metrics`)
- `sync-api-cors.sh` - Sync API CORS with frontend IP (still needed)
- `get-service-ips.sh` - Get current service IPs and ALB DNS name
- `force-redeploy-service.sh` - Force service redeployment
- `check-service-status.sh` - Diagnose service issues
- `diagnose-frontend.sh` - Troubleshoot frontend
- `fix-frontend-health.sh` - Fix frontend health checks
- `cleanup-infrastructure.sh` - Remove all infrastructure

### ⚠️ Can Delete (Replaced or One-Time Use)

- `check-why-service-not-created.sh` → **Delete** (one-time diagnostic, `create-services.sh` has better errors)
- `find-public-subnets.sh` → **Delete** (one-time setup, handled by `setup-infrastructure.sh`)

**Note**: Scripts related to frontend API URL syncing have been removed since ALB handles this automatically. The `sync-api-cors.sh` script is still needed for CORS configuration.

---

## 🚀 Quick Reference: New AWS Improvements

### S3 Storage Setup

**What it does**: S3 buckets are automatically created by `setup-infrastructure.sh` for persistent storage of queries, metrics, and logs.

**Steps** (if buckets weren't created automatically):
```bash
cd aws/scripts
# S3 buckets are created automatically in setup-infrastructure.sh ✅
# Just add IAM permissions (Step 7.5) and redeploy:
./force-redeploy-service.sh esa-iagen-api-service  # Apply permissions
```

**What gets stored**:
- Query/response history (JSONL, compressed)
- CloudWatch metrics exports
- Application logs (archived)
- Backups

**Cost**: ~$0.01-0.05/month (very low, first 5GB free)

### CloudWatch Advanced

**What it does**: Creates dashboards, alarms, and saved queries for better observability.

**Steps**:
```bash
cd aws/scripts
./setup-cloudwatch-advanced.sh
```

**What you get**:
- Dashboard with CPU, memory, response time, errors
- Alarms for high CPU (>80%), high memory (>85%), 5xx errors
- Log Insights saved queries for errors and RAG performance

**Cost**: $0 (dashboards and alarms are free)

**View**: https://console.aws.amazon.com/cloudwatch/home?region=YOUR_REGION#dashboards:name=esa-iagen-overview

### Auto-Scaling

**What it does**: Automatically scales API service based on CPU and memory usage.

**Steps**:
```bash
cd aws/scripts
./setup-autoscaling.sh
```

**Configuration**:
- Min: 1 task
- Max: 5 tasks
- Target CPU: 70%
- Target Memory: 80%

**Cost**: $0 (only pay for additional tasks when scaling up)

**Monitor**: https://console.aws.amazon.com/ecs/v2/clusters/esa-iagen-cluster/services/esa-iagen-api-service/auto-scaling

### Complete Setup Order

For a complete production-ready setup:

1. **Basic Infrastructure** (Steps 1-6):
   ```bash
   ./setup-infrastructure.sh          # Creates ALB, S3, VPC, etc.
   ./register-task-definitions.sh     # Registers tasks, sets ALB DNS
   ./create-services.sh               # Creates services, registers with ALB
   ./sync-api-cors.sh                 # Syncs CORS with frontend IP
   ```

2. **Advanced Features** (Steps 7-7.7):
   ```bash
   # S3 buckets already created in Step 1 ✅
   ./setup-cloudwatch-advanced.sh
   ./setup-autoscaling.sh
   ./force-redeploy-service.sh esa-iagen-api-service
   ```

3. **Verify**:
   ```bash
   ./get-service-ips.sh
   # Access application via ALB DNS name
   # Check CloudWatch dashboard
   # Verify auto-scaling is active
   # Check S3 bucket has folders created
   ```

**Total time**: ~15-20 minutes for complete setup

---

**Ready to deploy?** Follow the steps above and you'll have your application running on AWS ECS with production-ready monitoring and scaling! 🚀

