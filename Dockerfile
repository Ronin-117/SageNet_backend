# Use a modern Python version (3.11) to fix dependency errors
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Upgrade pip to the latest version immediately
RUN pip install --upgrade pip

# Copy requirements first (for caching)
COPY requirements.txt .

# Install dependencies (No cache to keep image small)
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code
COPY . .