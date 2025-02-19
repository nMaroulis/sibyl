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

RUN apt-get update && apt-get install -y build-essential gcc python3-dev

# for blis and spacy to work
RUN apt-get update && apt-get install -y \
    build-essential \
    libopenblas-dev \
    liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# install them manually since they crash in requirements.txt
#  RUN pip install --no-cache-dir --prefer-binary blis && \
#      pip install --no-cache-dir --prefer-binary thinc

# Expose the required ports
EXPOSE 8501 8000

# Run main.py to start both services
CMD ["python", "-u", "main.py"]