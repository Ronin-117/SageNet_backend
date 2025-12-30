FROM python:3.11-slim
WORKDIR /app
RUN pip install --upgrade pip
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Add current directory to PYTHONPATH so python can find 'app'
ENV PYTHONPATH=/app