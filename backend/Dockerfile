FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

# Copy source code
COPY src/ ./src/
COPY local_dev.py ./

# Expose port
EXPOSE 8000

# Run application
CMD ["python", "local_dev.py"]
