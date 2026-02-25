FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Download and install SCIP
# Using SCIP 9.2.0 - latest version compatible with academic/non-commercial use
RUN wget --progress=dot:giga --timeout=30 --tries=3 \
    https://github.com/scipopt/scip/releases/download/v920/SCIPOptSuite-9.2.0-Linux-ubuntu24.deb \
    && apt-get update \
    && apt-get install -y ./SCIPOptSuite-9.2.0-Linux-ubuntu24.deb \
    && rm SCIPOptSuite-9.2.0-Linux-ubuntu24.deb \
    && rm -rf /var/lib/apt/lists/*

# Install GLPK (free, open-source solver)
RUN apt-get update \
    && apt-get install -y glpk-utils \
    && rm -rf /var/lib/apt/lists/*

# Make SCIP non-critical
RUN scip --version || echo "WARNING: SCIP not available"
RUN glpsol --version

# Install Python package manager
RUN pip install --no-cache-dir uv

# Copy dependency files
COPY pyproject.toml uv.lock* ./

# Install Python dependencies
RUN uv pip install --system --no-cache -e .

# Copy application code
COPY esms/ esms/

# Create data directory for potential file operations
RUN mkdir -p /app/data

# Expose API port
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV LOG_LEVEL=INFO

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Run FastAPI server
CMD ["uvicorn", "esms.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
