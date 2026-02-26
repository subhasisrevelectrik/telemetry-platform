"""Lambda handler for FastAPI application using Mangum."""

from mangum import Mangum

from src.app import app

# Create Lambda handler - Mangum auto-detects HTTP API v2.0
handler = Mangum(app, lifespan="off")
