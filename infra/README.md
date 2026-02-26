# AWS Infrastructure - CDK Deployment

This directory contains AWS CDK (Cloud Development Kit) code to deploy the complete CAN Telemetry Platform to AWS.

## Architecture

The stack deploys:

- **S3 Buckets**: Data lake, Athena results, frontend hosting
- **AWS Glue**: Database and crawler for data catalog
- **AWS Athena**: Workgroup for querying telemetry data
- **Lambda Functions**: Decoder (CAN frame processing) and API backend
- **API Gateway**: REST API with throttling and CORS
- **Cognito**: User pool for authentication
- **CloudFront**: CDN for frontend distribution

## Prerequisites

1. **AWS Account**: Active AWS account with credentials configured
2. **AWS CLI**: Installed and configured (`aws configure`)
3. **Python 3.12+**: For CDK
4. **Node.js**: For AWS CDK CLI

## Installation

### 1. Install AWS CDK CLI

```bash
npm install -g aws-cdk
```

### 2. Install Python Dependencies

```bash
cd infra
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e .
```

### 3. Bootstrap CDK (First Time Only)

```bash
cdk bootstrap aws://ACCOUNT-NUMBER/REGION
```

Replace `ACCOUNT-NUMBER` with your AWS account ID and `REGION` with your preferred region (e.g., `us-east-1`).

## Deployment

### 1. Synthesize CloudFormation Template

```bash
cdk synth
```

This generates CloudFormation template and validates your code.

### 2. Deploy Stack

```bash
cdk deploy
```

You'll be prompted to approve security changes. Type `y` to proceed.

**Deployment time**: ~10-15 minutes

### 3. Note the Outputs

After deployment, note these outputs:
- `DataBucketName`: S3 bucket for telemetry data
- `ApiUrl`: API Gateway endpoint
- `CloudFrontDomain`: Frontend URL
- `UserPoolId`: Cognito user pool ID
- `UserPoolClientId`: Cognito app client ID

## Post-Deployment Setup

### 1. Upload DBC Files

```bash
aws s3 cp ../sample-data/dbc/ev_powertrain.dbc \
  s3://DATA_BUCKET_NAME/dbc/ev_powertrain.dbc
```

### 2. Run Glue Crawler

```bash
aws glue start-crawler --name telemetry-crawler
```

Wait for crawler to complete (~2-5 minutes):

```bash
aws glue get-crawler --name telemetry-crawler | grep State
```

### 3. Configure Edge Agent

Update `edge-agent/config.yaml`:

```yaml
s3:
  bucket: "DATA_BUCKET_NAME"  # From CDK output
  region: "us-east-1"
  prefix: "raw"
```

### 4. Deploy Frontend

Build and deploy frontend:

```bash
cd ../frontend
npm run build

aws s3 sync dist/ s3://FRONTEND_BUCKET_NAME/

# Invalidate CloudFront cache
aws cloudfront create-invalidation \
  --distribution-id DISTRIBUTION_ID \
  --paths "/*"
```

### 5. Create Cognito User (Optional)

```bash
aws cognito-idp admin-create-user \
  --user-pool-id USER_POOL_ID \
  --username admin@example.com \
  --user-attributes Name=email,Value=admin@example.com \
  --temporary-password TempPass123!
```

## Testing

### Test Decoder Lambda

Upload a test file:

```bash
aws s3 cp ../sample-data/raw/vehicle_id=VIN_TEST01/year=2026/month=02/day=12/20260212T232844Z_raw.parquet \
  s3://DATA_BUCKET_NAME/raw/vehicle_id=VIN_TEST01/year=2026/month=02/day=12/
```

Check CloudWatch Logs:

```bash
aws logs tail /aws/lambda/TelemetryStack-DecoderFunction --follow
```

### Test API

```bash
curl https://API_URL/health

curl https://API_URL/vehicles
```

## Cost Estimation

**Monthly costs for small deployment** (10 vehicles, 10 GB/month):

- S3 storage: $0.25
- S3 requests: $0.05
- Lambda decoder: $1.50
- Lambda API: $0.50
- Athena: $0.50
- API Gateway: $3.50
- Glue crawler: $0.44
- CloudFront: $1.00
- **Total**: ~$8/month

Costs scale with:
- Data volume (S3 storage)
- Query frequency (Athena)
- API requests (Lambda + API Gateway)

## Monitoring

### CloudWatch Dashboards

View metrics:
- Lambda invocations and errors
- API Gateway requests and latency
- S3 bucket size
- Athena query performance

### Alarms

Set up alarms:

```bash
# Lambda error rate > 5%
aws cloudwatch put-metric-alarm \
  --alarm-name decoder-errors \
  --metric-name Errors \
  --namespace AWS/Lambda \
  --statistic Sum \
  --period 300 \
  --threshold 5 \
  --comparison-operator GreaterThanThreshold

# API Gateway 5XX errors
aws cloudwatch put-metric-alarm \
  --alarm-name api-5xx \
  --metric-name 5XXError \
  --namespace AWS/ApiGateway \
  --statistic Sum \
  --period 300 \
  --threshold 10 \
  --comparison-operator GreaterThanThreshold
```

## Updating the Stack

Make changes to `stacks/telemetry_stack.py`, then:

```bash
cdk diff  # Preview changes
cdk deploy  # Apply changes
```

## Destroying the Stack

**WARNING**: This deletes all resources including data!

```bash
cdk destroy
```

Data bucket has `RETAIN` policy, so it won't be deleted automatically. Delete manually if needed:

```bash
aws s3 rb s3://DATA_BUCKET_NAME --force
```

## Troubleshooting

### Deployment Fails

Check CloudFormation events:

```bash
aws cloudformation describe-stack-events --stack-name TelemetryStack
```

### Lambda Layer Too Large

The decoder layer includes cantools and pyarrow which can be large. To reduce size:

1. Build layer separately with Docker:

```bash
cd processing/decoder
docker run --rm -v "$PWD":/var/task public.ecr.aws/lambda/python:3.12 \
  pip install -r requirements.txt -t python/
zip -r layer.zip python/
```

2. Upload to S3 and reference in CDK:

```python
self.decoder_layer = lambda_.LayerVersion(
    self,
    "DecoderLayer",
    code=lambda_.Code.from_bucket(bucket, "layers/decoder-layer.zip"),
    compatible_runtimes=[lambda_.Runtime.PYTHON_3_12],
)
```

### Athena Queries Fail

Ensure Glue crawler has run:

```bash
aws glue start-crawler --name telemetry-crawler
```

Check table schema:

```bash
aws glue get-table --database-name telemetry_db --name decoded
```

### API Returns 502

Check Lambda logs:

```bash
aws logs tail /aws/lambda/TelemetryStack-ApiFunction --follow
```

Ensure environment variables are set correctly in Lambda.

## Security Best Practices

1. **Enable MFA** on Cognito user pool
2. **Restrict CORS** to specific domains in production
3. **Enable CloudTrail** for audit logging
4. **Use VPC** for Lambda functions (optional)
5. **Enable S3 bucket logging**
6. **Rotate credentials** regularly
7. **Use AWS Secrets Manager** for sensitive config

## Architecture Diagram

```
┌─────────────┐
│  Vehicle    │
│  Edge Agent │
└──────┬──────┘
       │ Upload
       ▼
┌─────────────────────┐
│  S3 Data Lake       │
│  - raw/             │
│  - decoded/         │
│  - dbc/             │
└──────┬──────────────┘
       │
       ├─────────────────────┐
       │                     │
       ▼                     ▼
┌──────────────┐   ┌─────────────────┐
│ Decoder      │   │ Glue Crawler    │
│ Lambda       │   │ (Daily)         │
└──────┬───────┘   └────────┬────────┘
       │                    │
       ▼                    ▼
┌─────────────────────┐   ┌──────────────┐
│  S3 decoded/        │   │ Glue Catalog │
└─────────────────────┘   └──────┬───────┘
                                 │
                                 ▼
                          ┌──────────────┐
                          │   Athena     │
                          └──────┬───────┘
                                 │
                                 ▼
                          ┌──────────────┐
                          │ API Lambda   │
                          └──────┬───────┘
                                 │
                                 ▼
                          ┌──────────────┐
                          │ API Gateway  │
                          └──────┬───────┘
                                 │
                                 ▼
                          ┌──────────────┐
                          │  CloudFront  │
                          │  + Frontend  │
                          └──────────────┘
```

## Next Steps

1. **Deploy stack**: `cdk deploy`
2. **Upload DBC files**: See post-deployment setup
3. **Run crawler**: Initialize Glue catalog
4. **Test API**: Verify endpoints work
5. **Deploy frontend**: Build and upload to S3
6. **Configure edge agents**: Point to S3 bucket
7. **Monitor**: Set up CloudWatch dashboards

---

**Stack Name**: TelemetryStack
**Region**: us-east-1 (configurable)
**Estimated Cost**: $8-50/month depending on usage
