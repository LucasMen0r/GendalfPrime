FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY app_python/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the full project
COPY . /app/

# Make app_python importable both as a package and bare module
ENV PYTHONPATH="/app:/app/app_python"

# Expose Django dev server port
EXPOSE 8000

# Default command (overridable in compose.yaml)
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
