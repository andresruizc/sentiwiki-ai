# AWS IAM Requirements

This document outlines all IAM policies and permissions required to deploy and run the SentiWiki AI system on AWS ECS Fargate.

## Overview

There are **two types of IAM roles** you need to configure:

1. **IAM User/Role for Deployment** - Permissions for running deployment scripts (your local machine or CI/CD)
2. **ECS Task Execution Role** - Permissions for ECS tasks to access AWS services (Secrets Manager, S3, CloudWatch)

---

## 1. IAM User/Role for Deployment Scripts

**Who needs this**: The IAM user or role you use to run deployment scripts (e.g., `setup-infrastructure.sh`, `register-task-definitions.sh`).

**When**: Before running any deployment commands.

### Required Permissions

This policy grants all permissions needed to create and manage AWS infrastructure:

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
        "ec2:DeleteSecurityGroup",
        "ec2:DescribeNetworkInterfaces",
        "ec2:CreateNetworkInterface",
        "ec2:DeleteNetworkInterface",
        "ec2:DescribeRouteTables",
        "ec2:DescribeInternetGateways",
        "ec2:CreateInternetGateway",
        "ec2:AttachInternetGateway",
        "ec2:CreateRoute",
        "ec2:CreateRouteTable",
        "ec2:AssociateRouteTable"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ELBLoadBalancer",
      "Effect": "Allow",
      "Action": [
        "elasticloadbalancing:*"
      ],
      "Resource": "*"
    },
    {
      "Sid": "CloudWatchLogs",
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:DescribeLogGroups",
        "logs:DeleteLogGroup",
        "logs:PutRetentionPolicy"
      ],
      "Resource": "*"
    },
    {
      "Sid": "SecretsManager",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:CreateSecret",
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret",
        "secretsmanager:PutSecretValue",
        "secretsmanager:UpdateSecret"
      ],
      "Resource": "arn:aws:secretsmanager:*:YOUR_ACCOUNT_ID:secret:esa-iagen/*"
    },
    {
      "Sid": "S3Access",
      "Effect": "Allow",
      "Action": [
        "s3:CreateBucket",
        "s3:GetBucketLocation",
        "s3:ListBucket",
        "s3:PutBucketPolicy",
        "s3:GetBucketPolicy",
        "s3:PutBucketVersioning",
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::esa-iagen-*",
        "arn:aws:s3:::esa-iagen-*/*"
      ]
    },
    {
      "Sid": "IAMRoleManagement",
      "Effect": "Allow",
      "Action": [
        "iam:CreateRole",
        "iam:AttachRolePolicy",
        "iam:PutRolePolicy",
        "iam:GetRole",
        "iam:GetRolePolicy",
        "iam:ListRolePolicies",
        "iam:ListAttachedRolePolicies",
        "iam:PassRole"
      ],
      "Resource": [
        "arn:aws:iam::YOUR_ACCOUNT_ID:role/ecsTaskExecutionRole",
        "arn:aws:iam::YOUR_ACCOUNT_ID:role/ecsTaskRole"
      ]
    }
  ]
}
```

### How to Apply

**Via AWS Console:**

1. Go to **IAM Console** → **Users** (or **Roles** if using a role)
2. Select your user/role (e.g., `github-actions-ci-cd` for CI/CD)
3. Click **Add permissions** → **Attach policies directly**
4. Click **Create policy**
5. Switch to **JSON** tab
6. Paste the policy above (replace `YOUR_ACCOUNT_ID` with your AWS Account ID)
7. Click **Next** → Name it `ESAIAGenDeploymentPolicy`
8. Click **Create policy**
9. Go back to the user/role and attach the new policy

**Via AWS CLI:**

```bash
# Create the policy
aws iam create-policy \
  --policy-name ESAIAGenDeploymentPolicy \
  --policy-document file://deployment-policy.json \
  --region YOUR_REGION

# Attach to user
aws iam attach-user-policy \
  --user-name YOUR_USERNAME \
  --policy-arn arn:aws:iam::YOUR_ACCOUNT_ID:policy/ESAIAGenDeploymentPolicy
```

**Important Notes:**
- Replace `YOUR_ACCOUNT_ID` with your actual AWS Account ID
- The `iam:PassRole` permission is **critical** - without it, ECS task registration will fail
- For production, consider restricting resources (e.g., specific ECS clusters, S3 buckets) instead of using `*`

---

## 2. ECS Task Execution Role

**Who needs this**: The IAM role that ECS uses to pull images, write logs, and access secrets when running tasks.

**Role name**: `ecsTaskExecutionRole` (created automatically by `setup-infrastructure.sh`)

**When**: After infrastructure setup, before services start.

### 2.1 Secrets Manager Access

**Why**: Tasks need to read API keys from Secrets Manager.

**Policy** (add as inline policy to `ecsTaskExecutionRole`):

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
        "arn:aws:secretsmanager:YOUR_REGION:YOUR_ACCOUNT_ID:secret:esa-iagen/ANTHROPIC_API_KEY-*",
        "arn:aws:secretsmanager:YOUR_REGION:YOUR_ACCOUNT_ID:secret:esa-iagen/OPENAI_API_KEY-*",
        "arn:aws:secretsmanager:YOUR_REGION:YOUR_ACCOUNT_ID:secret:GRAFANA_ADMIN_PASSWORD-*"
      ]
    }
  ]
}
```

**How to Apply:**

1. Go to **IAM Console** → **Roles** → `ecsTaskExecutionRole`
2. Click **Add permissions** → **Create inline policy**
3. Switch to **JSON** tab
4. Paste the policy above (replace `YOUR_REGION` and `YOUR_ACCOUNT_ID`)
5. Name it: `ECSSecretsAccess`
6. Click **Create policy**

**Important Notes:**
- Replace `YOUR_REGION` with your AWS region (e.g., `eu-north-1`, `us-east-1`)
- Replace `YOUR_ACCOUNT_ID` with your AWS Account ID
- The `-*` suffix is required because Secrets Manager adds random characters to ARNs
- `kms:Decrypt` is needed if using custom KMS keys (optional but recommended)

### 2.2 S3 and CloudWatch Access (Optional)

**Why**: If your application writes logs to S3 or sends metrics to CloudWatch.

**Policy** (add as inline policy to `ecsTaskExecutionRole`):

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

**How to Apply:**

1. Go to **IAM Console** → **Roles** → `ecsTaskExecutionRole`
2. Click **Add permissions** → **Create inline policy**
3. Switch to **JSON** tab
4. Paste the policy above
5. Name it: `ESAIAGenS3CloudWatchPolicy`
6. Click **Create policy**

---

## 3. Quick Reference Checklist

Before running deployment scripts, ensure:

- [ ] **Deployment IAM User/Role** has the deployment policy attached
- [ ] **`ecsTaskExecutionRole`** exists (created by `setup-infrastructure.sh`)
- [ ] **`ecsTaskExecutionRole`** has `ECSSecretsAccess` inline policy for Secrets Manager
- [ ] **`ecsTaskExecutionRole`** has `ESAIAGenS3CloudWatchPolicy` inline policy (if using S3/CloudWatch)
- [ ] All ARNs in policies use your actual **Account ID** and **Region**

---

## 4. Common Errors and Solutions

### Error: `AccessDeniedException` when registering task definitions

**Cause**: Missing `iam:PassRole` permission on deployment user/role.

**Fix**: Add the deployment policy (Section 1) to your IAM user/role.

### Error: `AccessDeniedException` when ECS tasks start

**Cause**: `ecsTaskExecutionRole` cannot read Secrets Manager.

**Fix**: Add `ECSSecretsAccess` inline policy (Section 2.1) to `ecsTaskExecutionRole`.

### Error: `AccessDeniedException` when writing to S3

**Cause**: `ecsTaskExecutionRole` lacks S3 permissions.

**Fix**: Add `ESAIAGenS3CloudWatchPolicy` inline policy (Section 2.2) to `ecsTaskExecutionRole`.

---

## 5. Security Best Practices

1. **Principle of Least Privilege**: Only grant permissions needed for specific resources
2. **Use Resource ARNs**: Replace `*` with specific resource ARNs when possible
3. **Separate Roles**: Use different roles for deployment vs. runtime
4. **Regular Audits**: Review IAM policies periodically
5. **Enable CloudTrail**: Monitor IAM policy changes

---

## 6. Additional Resources

- [AWS IAM Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html)
- [ECS Task Execution Role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task_execution_IAM_role.html)
- [Secrets Manager IAM Policies](https://docs.aws.amazon.com/secretsmanager/latest/userguide/reference_iam-permissions.html)

---

**Need help?** See [`AWS_DEPLOYMENT_GUIDE.md`](AWS_DEPLOYMENT_GUIDE.md) for step-by-step deployment instructions.

