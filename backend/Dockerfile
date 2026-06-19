FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies needed for chromadb, faiss, and related packages
RUN apt-get update && apt-get install -y \
    bash \
    curl \
    gcc \
    g++ \
    cmake \
    python3-dev \
    libffi-dev \
    libssl-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for Docker layer caching
COPY requirements.txt .

# Install a CPU-only torch build first so sentence-transformers
# does not pull CUDA wheels inside the container.
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    torch==2.5.1+cpu

# Install all Python dependencies
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy all backend source code
COPY . .

# Create necessary directories
RUN mkdir -p data reports rag/chroma_store

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s \
    --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start FastAPI with uvicorn
CMD ["python", "-m", "uvicorn", "main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000"]
