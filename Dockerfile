# Use the official Python 3.12 slim image
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Copy the application code to the container
COPY sibyl/ .

# Install dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Expose the required ports
EXPOSE 8501 8000

# Run main.py to start both services
CMD ["python", "main.py"]