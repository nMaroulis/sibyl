# Option 1: Use the official Python 3.12 slim image
# FROM python:3.12-slim
# Option 2: Force AMD64 to avoid ARM-related package issues
FROM --platform=linux/amd64 python:3.12

# Set the working directory in the container
WORKDIR /app

# Copy the application code to the container
COPY . .

# Set environment variables to avoid Python cache and force UTF-8
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=UTF-8 \
    PIP_NO_CACHE_DIR=1 \
    UV_CACHE_DIR="/tmp/uv-cache"

# Install system dependencies and build tools
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    python3-dev \
    libopenblas-dev \
    libffi-dev \
    libblas-dev \
    liblapack-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -Ls https://astral.sh/uv/install.sh | sh

# Add uv to PATH
ENV PATH="/root/.cargo/bin:$PATH"

# Optional: verify uv installation
RUN uv --version

# Upgrade pip, setuptools, and wheel
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Sync dependencies
RUN uv sync

# Expose the required ports
EXPOSE 8501 8000 50051

# Run main.py to start both services
CMD ["python", "-u", "main.py"]