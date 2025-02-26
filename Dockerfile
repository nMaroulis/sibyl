# Use the official Python 3.12 slim image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Copy the application code to the container
COPY . .

# Set environment variables to avoid Python cache and force UTF-8
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=UTF-8 \
    PIP_NO_CACHE_DIR=1

# Install system dependencies and build tools
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    python3-dev \
    libopenblas-dev \
    liblapack-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

# Set Poetry configuration to not create a virtualenv (optional)
RUN poetry config virtualenvs.create false

# Add Poetry to PATH
ENV PATH="/root/.local/bin:$PATH"

# Ensure poetry is correctly installed
RUN poetry --version

# Upgrade pip, setuptools, and wheel
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install dependencies via Poetry
RUN poetry install --no-interaction # --without dev

# Expose the required ports
EXPOSE 8501 8000

# Run main.py to start both services
CMD ["poetry", "run", "python", "-u", "main.py"]