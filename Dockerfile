# Set the working directory for the application
# Use a Python base image
FROM python:3.11 AS base

# Set the working directory for the application
WORKDIR /app/sibyl

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    software-properties-common \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy the Conda environment file
COPY sibyl/conda_env.yml .

# Create the Conda environment
RUN conda env create -f conda_env.yml && conda clean -afy

# Use a Python base image for frontend
FROM base AS frontend

# Set the working directory for frontend
WORKDIR /app/sibyl/frontend

# Copy the frontend code to the container
COPY sibyl/frontend/ .

# Activate the Conda environment and run the frontend
CMD ["/bin/bash", "-c", "conda run -n sibyl streamlit run --server.port 8501 home_page.py"]

# Use a Python base image for backend
FROM base AS backend

# Set the working directory for backend
WORKDIR /app/sibyl/backend

# Copy the backend code to the container
COPY sibyl/backend/ .

# Expose the port for the backend
EXPOSE 8000

# Activate the Conda environment and run the backend
CMD ["/bin/bash", "-c", "conda run -n sibyl python rest_server.py"]
