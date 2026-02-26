# CAN Bus Telemetry Platform - Architecture

## System Overview

The CAN Bus Telemetry Platform is a distributed system for capturing, processing, storing, and visualizing vehicle telemetry data from CAN bus networks.

## Components

### 1. Edge Agent (Vehicle Side)

**Technology**: Python 3.12+

**Responsibilities**:
- Read CAN frames from hardware interface (SocketCAN, PCAN) or simulate
- Batch frames into time windows (default: 60 seconds)
- Convert to Parquet format with schema validation
- Upload to S3 with retry logic and offline buffering
- Monitor disk space and evict old data if necessary

**Data Flow**:
```
CAN Interface → CANFrame objects → Time-windowed batches → PyArrow Table → Parquet file → S3 upload
```

**Schema - Raw CAN Parquet**:
```
timestamp: timestamp[ns]     # Nanosecond precision timestamp
arb_id: uint32              # CAN arbitration ID
dlc: uint8                  # Data length code (0-8)
data: binary                # Raw CAN data bytes
vehicle_id: string          # Vehicle identifier
```

**Output Path Pattern**:
```
s3://bucket/raw/vehicle_id={VIN}/year={YYYY}/month={MM}/day={DD}/{timestamp}_raw.parquet
```

### 2. Decoder Lambda (Cloud Processing)

**Technology**: Python 3.12, AWS Lambda

**Trigger**: S3 PUT event on `raw/` prefix

**Responsibilities**:
- Download raw Parquet file from S3
- Load DBC file from S3 (cached in /tmp)
- Decode each CAN frame using cantools
- Handle decode errors gracefully (log and skip)
- Validate decoded values against DBC min/max
- Write decoded signals to Parquet
- Maintain partition alignment with input

**Data Flow**:
```
S3 Event → Download raw Parquet → Load DBC → Decode frames → Validate → Write decoded Parquet → S3 PUT
```

**Schema - Decoded Signals Parquet**:
```
timestamp: timestamp[ns]     # Original CAN frame timestamp
vehicle_id: string          # Vehicle identifier
message_name: string        # CAN message name (from DBC)
signal_name: string         # Signal name (from DBC)
value: float64              # Decoded physical value
unit: string                # Engineering unit (from DBC)
```

**Performance**:
- Memory: 1024 MB
- Timeout: 5 minutes
- Typical execution: 2-3 seconds for 10 MB file
- Cold start: ~5 seconds (with layer)

### 3. Data Lake (S3 + Glue + Athena)

**S3 Bucket Structure**:
```
telemetry-data-lake/
├── raw/
│   └── vehicle_id=X/year=Y/month=M/day=D/*.parquet
├── decoded/
│   └── vehicle_id=X/year=Y/month=M/day=D/*.parquet
└── dbc/
    └── *.dbc
```

**Glue Catalog**:
- Database: `telemetry_db`
- Tables:
  - `raw_can_frames`: External table pointing to `raw/`
  - `decoded_signals`: External table pointing to `decoded/`

**Athena Workgroup**:
- Query result location: `s3://athena-results/`
- Encryption: SSE-S3
- Result caching: Enabled (24 hours)

**Partitioning Strategy**:
- Hive-style partitioning by `vehicle_id`, `year`, `month`, `day`
- Reduces query scan size by 100-1000x for typical queries
- Partition pruning based on WHERE clauses

### 4. Backend API (FastAPI)

**Technology**: Python 3.12, FastAPI, boto3

**Deployment Modes**:
1. **Local Development**: Uvicorn server, reads from `./data/decoded/`
2. **AWS Lambda**: Mangum adapter, queries Athena

**Endpoints**:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/vehicles` | List all vehicles with metadata |
| GET | `/vehicles/{id}/sessions` | Get recording sessions (by day) |
| GET | `/vehicles/{id}/messages` | Get available CAN messages |
| GET | `/vehicles/{id}/messages/{msg}/signals` | Get signals in a message |
| POST | `/vehicles/{id}/query` | Time-series query with downsampling |

**Query Endpoint Details**:

Request:
```json
{
  "signals": [
    {"message_name": "BMS_PackStatus", "signal_name": "Pack_SOC"}
  ],
  "start_time": "2025-02-12T14:00:00Z",
  "end_time": "2025-02-12T14:10:00Z",
  "max_points": 2000
}
```

Response:
```json
{
  "signals": [
    {
      "name": "Pack_SOC",
      "unit": "%",
      "data": [
        {"t": 1707746400000, "v": 85.5},
        {"t": 1707746401000, "v": 85.4}
      ]
    }
  ],
  "query_stats": {
    "rows_scanned": 60000,
    "bytes_scanned": 245760,
    "duration_ms": 1234
  }
}
```

**LTTB Downsampling**:

When query returns > `max_points` per signal:
1. Group points by signal
2. Apply Largest Triangle Three Buckets algorithm
3. Preserve visual characteristics (peaks, troughs, trends)
4. Return exactly `max_points` per signal

**Local Mode**:

Set `LOCAL_MODE=true` environment variable:
- Reads Parquet files from `./data/decoded/` using PyArrow
- No AWS credentials required
- Simulates Athena query behavior
- Used for development and testing

### 5. Frontend Dashboard (React + TypeScript)

**Technology**: React 18, TypeScript, Vite, TanStack Query, uPlot, Zustand, Tailwind CSS

**Features**:
- Vehicle selection dropdown
- Time range picker with session-aware calendar
- Message and signal selection with search
- Multi-series time-series chart with dual Y-axes
- Zoom, pan, crosshair tooltips
- CSV and PNG export
- Signal statistics panel

**State Management**:

Zustand store:
```typescript
{
  selectedVehicle: string | null
  selectedMessages: string[]
  selectedSignals: Signal[]
  timeRange: { start: Date, end: Date }
  chartConfig: { maxPoints: number, showGrid: boolean }
}
```

**Data Fetching**:

TanStack Query hooks:
- `useVehicles()`: List vehicles (refetch on mount)
- `useSessions(vehicleId)`: List sessions (cached 5 min)
- `useMessages(vehicleId)`: List messages (cached 5 min)
- `useSignals(vehicleId, messageName)`: List signals (cached 5 min)
- `useSignalQuery(vehicleId, params)`: Time-series query (no cache)

**Chart Performance**:

uPlot optimizations:
- Canvas-based rendering (60fps with 100K points)
- Sparse series support (different sample rates)
- Dual Y-axis for different units
- Cursor sync across series
- Efficient redraw on zoom/pan

### 6. Infrastructure (AWS CDK)

**Resources Created**:

- **S3 Buckets**: 3 (data lake, frontend, Athena results)
- **Lambda Functions**: 6 (decoder + 5 API handlers)
- **API Gateway**: REST API with CORS and throttling
- **Cognito**: User pool and app client
- **CloudFront**: Distribution for frontend
- **Glue**: Database, 2 tables, crawler
- **Athena**: Workgroup with result location
- **IAM Roles**: Lambda execution roles with least privilege

**Stack Outputs**:
```
TelemetryStack.ApiUrl = https://xxx.execute-api.region.amazonaws.com/prod
TelemetryStack.CloudFrontDomain = xxx.cloudfront.net
TelemetryStack.DataBucket = telemetry-data-lake-xxx
TelemetryStack.CognitoUserPoolId = region_xxx
TelemetryStack.CognitoClientId = xxx
```

## Data Flow Diagrams

### Capture Flow

```
┌─────────────┐
│  CAN Bus    │
└──────┬──────┘
       │ CAN frames (100-1000 Hz)
       ▼
┌─────────────┐
│ Edge Agent  │
│ - Read      │
│ - Batch     │
│ - Convert   │
└──────┬──────┘
       │ Every 60s
       ▼
┌─────────────┐
│ Local File  │
│ .parquet    │
└──────┬──────┘
       │ Upload when online
       ▼
┌─────────────┐
│  S3 raw/    │
└─────────────┘
```

### Processing Flow

```
┌─────────────┐
│  S3 raw/    │
│  new file   │
└──────┬──────┘
       │ S3 PUT event
       ▼
┌─────────────────────┐
│ Decoder Lambda      │
│ 1. Download raw     │
│ 2. Load DBC         │
│ 3. Decode frames    │
│ 4. Validate         │
│ 5. Write decoded    │
└──────┬──────────────┘
       │
       ▼
┌─────────────┐
│ S3 decoded/ │
└──────┬──────┘
       │ Daily
       ▼
┌─────────────┐
│Glue Crawler │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│Glue Catalog │
│ Tables      │
└─────────────┘
```

### Query Flow

```
┌─────────────┐
│  Frontend   │
│  User       │
└──────┬──────┘
       │ HTTP POST /query
       ▼
┌─────────────────┐
│  API Gateway    │
│  + Cognito Auth │
└──────┬──────────┘
       │
       ▼
┌─────────────────────┐
│  API Lambda         │
│  1. Build SQL       │
│  2. Query Athena    │
│  3. Poll results    │
│  4. Downsample      │
└──────┬──────────────┘
       │ SQL
       ▼
┌──────────────────┐
│  Athena          │
│  - Scan S3       │
│  - Filter        │
│  - Aggregate     │
└──────┬───────────┘
       │ Results
       ▼
┌─────────────────────┐
│  API Lambda         │
│  Format & return    │
└──────┬──────────────┘
       │ JSON
       ▼
┌─────────────┐
│  Frontend   │
│  Render     │
└─────────────┘
```

## Scalability

### Edge Agent

- **CAN Frame Rate**: 1000+ msg/sec
- **Batch Window**: Configurable (default 60s)
- **File Size**: ~1-10 MB per batch
- **Offline Buffer**: Limited by disk space
- **Upload Concurrency**: 1 file at a time (sequential)

### Decoder Lambda

- **Concurrency**: Auto-scales to 1000 concurrent executions
- **Throughput**: ~500 files/minute at scale
- **File Size Limit**: 10 MB recommended (Lambda memory)
- **Batch Processing**: Use Glue job for large backlogs

### Data Lake

- **Storage**: Unlimited (S3)
- **Partition Limit**: 10M partitions per table (Glue)
- **Query Concurrency**: 25 queries (Athena per account limit)
- **Data Scanned**: Reduced by partitioning (10-100x)

### API

- **Requests/sec**: 100 (throttled by usage plan)
- **Burst**: 1000 requests
- **Lambda Concurrency**: 10 (reserved)
- **Query Timeout**: 30 seconds
- **Downsampling**: O(n) algorithm, ~100K points/sec

### Frontend

- **Chart Points**: 100K+ rendered smoothly
- **Concurrent Users**: Limited by CloudFront (high)
- **Cache Hit Ratio**: 70-90% typical

## Security Architecture

### Edge Agent

- **Credentials**: IAM user with S3 PutObject only
- **Encryption**: TLS 1.2+ for S3 uploads
- **Secrets**: Vehicle ID in config file (not sensitive)

### S3

- **Encryption at Rest**: SSE-S3 (or SSE-KMS for compliance)
- **Versioning**: Enabled (protects against accidental deletes)
- **Lifecycle**: Auto-archive to Glacier after 90 days
- **Access**: Bucket policy allows only Lambda and Athena

### Lambda

- **Execution Role**: Read S3 (data + DBC), Write S3 (decoded), CloudWatch Logs
- **Network**: Public (or VPC for sensitive data)
- **Environment Variables**: DBC_BUCKET, DBC_KEY (not encrypted, not sensitive)

### API Gateway

- **Authorizer**: Cognito user pool
- **Throttling**: 100 req/sec, 1000 burst
- **CORS**: Restricted to CloudFront domain (prod) or localhost (dev)
- **TLS**: 1.2+ enforced

### Cognito

- **Password Policy**: 8+ chars, uppercase, lowercase, number
- **MFA**: Optional (recommended for production)
- **Token Expiration**: 1 hour access token, 30 day refresh

### Frontend

- **Hosting**: S3 + CloudFront (HTTPS only)
- **OAI**: CloudFront Origin Access Identity (S3 not public)
- **Headers**: Security headers (CSP, X-Frame-Options, etc.)

## Cost Estimation

### Small Fleet (10 vehicles)

**Assumptions**:
- 10 vehicles × 100 CAN msg/sec × 60s batches = 600 KB/batch/vehicle
- 10 uploads/hour/vehicle × 24 hours × 30 days = 7,200 files/month
- 7,200 files × 600 KB = 4.3 GB raw/month
- Decoded: ~5 GB/month
- Queries: 1000 queries/month, 100 MB scanned avg

**Monthly Costs**:
- S3 storage: $0.25 (9 GB × $0.023)
- S3 requests: $0.04 (7,200 PUT + 7,200 GET)
- Lambda decoder: $1.50 (7,200 invocations × 2 sec × $0.0000166667/GB-sec)
- Lambda API: $0.50 (1,000 invocations × 1 sec)
- Athena: $0.50 (1,000 queries × 100 MB × $5/TB)
- API Gateway: $3.50 (1,000 requests × $3.50/million)
- Glue crawler: $0.44 (monthly crawl × $0.44/DPU-hour)
- CloudFront: $1.00 (minimal traffic)

**Total**: ~$8/month

### Medium Fleet (100 vehicles)

- **Data**: 90 GB/month
- **Total**: ~$60/month

### Large Fleet (1000 vehicles)

- **Data**: 900 GB/month
- **Total**: ~$450/month

## Monitoring and Observability

### CloudWatch Metrics

**Edge Agent** (custom metrics):
- `UploadSuccess`: Count of successful uploads
- `UploadFailure`: Count of failed uploads
- `QueueDepth`: Number of pending files
- `DiskUsagePercent`: Local storage utilization

**Lambda Decoder**:
- `Invocations`: Total executions
- `Errors`: Failed executions
- `Duration`: Execution time (p50, p99)
- `Throttles`: Rate limit hits
- Custom: `FramesDecoded`, `DecodeErrors`

**API Lambda**:
- `Invocations`, `Errors`, `Duration`
- Custom: `AthenaQueryDuration`, `BytesScanned`, `RowsReturned`

**API Gateway**:
- `Count`: Total requests
- `4XXError`, `5XXError`
- `Latency`: Request duration (p50, p99)

**Athena**:
- `DataScannedInBytes`: Cost driver
- `EngineExecutionTime`
- `TotalExecutionTime`

### CloudWatch Logs

- Edge agent: Local file + CloudWatch agent (optional)
- Lambda: Automatic (7 day retention default, increase for prod)
- API Gateway: Access logs (optional)

### Alarms

**Critical**:
- Lambda error rate > 5%
- API Gateway 5XX rate > 1%
- S3 bucket size > 100 GB (cost control)

**Warning**:
- Decoder duration > 5 seconds (p99)
- Athena bytes scanned > 10 GB/day
- Edge agent upload failures > 10/hour

## Disaster Recovery

### Data Loss Prevention

- **S3 Versioning**: Enabled (recover from accidental delete)
- **Cross-Region Replication**: Optional for critical data
- **Backup**: S3 lifecycle to Glacier Deep Archive

### Recovery Point Objective (RPO)

- **Edge Agent**: Up to 1 batch window (60 seconds) if device fails
- **S3 Data**: 0 (versioned, durable)
- **Glue Catalog**: Recreate with crawler (~10 minutes)

### Recovery Time Objective (RTO)

- **Infrastructure**: Redeploy with CDK (~15 minutes)
- **Data Lake**: Immediate (S3 always available)
- **API**: Redeploy Lambda functions (~5 minutes)
- **Frontend**: Redeploy to S3 + invalidate CloudFront (~10 minutes)

## Testing Strategy

### Unit Tests

- **Edge Agent**: Mock CAN interface, test batching logic
- **Decoder**: Test DBC parsing, frame decoding, error handling
- **Backend**: Mock Athena client, test SQL generation, downsampling
- **Frontend**: Component tests with React Testing Library

### Integration Tests

- **Edge → S3**: Upload sample Parquet, verify S3 object
- **Decoder**: Trigger with sample S3 event, verify output
- **API → Athena**: Query with sample data, verify response
- **Frontend → API**: E2E with Cypress (optional)

### Performance Tests

- **Decoder Lambda**: Load test with 100+ concurrent invocations
- **API**: JMeter/Locust with 100 req/sec sustained
- **Frontend**: Lighthouse performance audit

### Local Testing

All components have local testing modes:
- Edge agent: `--simulate` flag
- Decoder: Process local files
- Backend: `LOCAL_MODE=true`
- Frontend: Vite dev server

## Future Enhancements

### Real-Time Streaming

Replace batch upload with Kinesis Data Streams:
- Edge agent → Kinesis producer
- Kinesis Firehose → S3 (buffered)
- Lambda triggered by Kinesis (real-time processing)

### Anomaly Detection

- SageMaker model training on historical signals
- Lambda inference on new data
- SNS notifications for anomalies

### Fleet Analytics

- Aggregate statistics across vehicles
- Comparative analysis (vehicle A vs. fleet avg)
- Trend detection over time

### Video Synchronization

- Upload dashcam video with timestamps
- Synchronize playback with telemetry chart
- Annotate video with signal overlays

### Mobile App

- React Native app with similar UI
- Push notifications for alerts
- Offline chart viewing (cached data)

---

**Document Version**: 1.0
**Last Updated**: 2025-02-12
**Author**: CAN Telemetry Platform Team
