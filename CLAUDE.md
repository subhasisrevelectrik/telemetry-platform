# CLAUDE.md - Project Intelligence for Claude Code

## Project: CAN Bus Telemetry Platform
Real-time vehicle CAN bus data telemetry and visualization platform.
Captures CAN frames -> batches to Parquet -> uploads to S3 -> Lambda decodes via DBC -> Athena queries -> FastAPI serves -> React dashboard visualizes.

## Security Rules (CRITICAL - READ FIRST)
- NEVER hardcode AWS credentials, API keys, tokens, or secrets in ANY file
- NEVER commit .env, set_aws_env.bat, set_aws_env.sh, or any file with real credentials
- NEVER pass credentials explicitly to boto3 - always use the default credential chain
- Preferred auth: `aws login` (uses SignInLocalDevelopmentAccess, short-lived tokens)
- IAM user: Shadow
- Before ANY commit, verify no secrets are included
- If you need to reference a credential in code, use: os.environ.get("VAR_NAME")

## AWS Services Used
S3 (data lake), Lambda (decoder + API), API Gateway, Cognito (auth), Glue (crawler + catalog), Athena (queries), CloudFront (frontend CDN), CDK (infrastructure)

## Tech Stack
- Edge Agent: Python 3.12+, cantools, pyarrow, boto3
- Processing: Python Lambda, cantools, pyarrow
- Backend: FastAPI, boto3, pyarrow, LTTB downsampling
- Frontend: React 19, TypeScript 5.8, Vite 7, Tailwind CSS, Plotly.js, Zustand, TanStack Query
- Infrastructure: AWS CDK (Python)
- CAN Protocols: J1939, UDS, DBC file format

## Project Layout
- edge-agent/ - CAN capture, simulation, Parquet batching, S3 upload
- infra/ - CDK stacks (only .example credential files committed)
- processing/ - Lambda decoder
- backend/ - FastAPI REST API (LOCAL_MODE=true for local dev)
- frontend/ - React dashboard (Vite dev server on :5173)
- sample-data/ - DBC files + sample Parquet data
- scripts/ - Dev utilities (dev-setup.sh, run-local.sh, run-tests.sh)
- data/ - Local dev data (gitignored)

## Development Setup
1. Clone repo
2. Run `aws login` to authenticate (recommended)
3. Run ./scripts/dev-setup.sh
4. Generate sample data: cd sample-data/scripts && python generate_sample_data.py
5. Run local stack: ./scripts/run-local.sh
6. Frontend: http://localhost:5173 | API docs: http://localhost:8000/docs

## Key Patterns
- Local dev uses LOCAL_MODE=true - no AWS needed for basic dev/testing
- Edge agent --simulate flag for dev without CAN hardware
- boto3 credential chain: aws login -> env vars -> ~/.aws/credentials -> IAM role
- Docker Compose available for quick local startup: docker-compose up
- CDK deployment: cd infra && cdk deploy
