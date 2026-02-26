"""FastAPI application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .models import HealthResponse
from .routers import messages, query, sessions, signals, vehicles

# Create FastAPI app
app = FastAPI(
    title="CAN Telemetry API",
    description="REST API for querying CAN bus telemetry data",
    version="1.0.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(vehicles.router, prefix="/vehicles", tags=["vehicles"])
app.include_router(sessions.router, prefix="/vehicles", tags=["sessions"])
app.include_router(messages.router, prefix="/vehicles", tags=["messages"])
app.include_router(signals.router, prefix="/vehicles", tags=["signals"])
app.include_router(query.router, prefix="/vehicles", tags=["query"])


@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint redirect to docs."""
    return {"message": "CAN Telemetry API - visit /docs for API documentation"}


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        mode="local" if settings.local_mode else "cloud",
    )
