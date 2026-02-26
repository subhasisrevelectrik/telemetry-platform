FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files
COPY pyproject.toml ./

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e .

# Copy source code
COPY src/ ./src/
COPY config.yaml ./

# Create data directories
RUN mkdir -p data/archive data/pending logs

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run edge agent
CMD ["python", "-m", "src.main", "--config", "config.yaml"]
