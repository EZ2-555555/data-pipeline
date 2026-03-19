FROM python:3.11-slim

WORKDIR /app

# Install CPU-only PyTorch first (much smaller than full PyTorch)
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/

CMD ["python", "-m", "src.scheduler"]
