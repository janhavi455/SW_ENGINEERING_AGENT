FROM python:3.11-slim

# Install system utilities and Git
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and install standard build & testing tools
RUN pip install --no-cache-dir --upgrade pip pytest setuptools wheel

# Create dedicated workspace directory
WORKDIR /workspace

CMD ["tail", "-f", "/dev/null"]
