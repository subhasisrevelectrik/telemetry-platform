"""Lambda handler for FastAPI application using Mangum."""

from mangum import Mangum

from src.app import app

# Create Lambda handler - Mangum auto-detects HTTP API v2.0
_mangum_handler = Mangum(app, lifespan="off")


def handler(event, context):
    # Async chat job — invoked via InvocationType='Event', not HTTP
    if event.get("_job_type") == "chat_process":
        from src.routers.chat import process_chat_job_async

        process_chat_job_async(event)
        return {"statusCode": 200}

    # Normal HTTP request via API Gateway
    return _mangum_handler(event, context)
