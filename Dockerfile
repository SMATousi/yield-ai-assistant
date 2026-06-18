FROM python:3.11-slim

WORKDIR /app

COPY requirements-app.txt .
RUN pip install --no-cache-dir -r requirements-app.txt

COPY config.py .
COPY src/ src/

EXPOSE 7860

# Data directory must be mounted at runtime:
#   docker run -v /path/to/data:/data -e YIELD_DATA_DIR=/data ...
ENV YIELD_DATA_DIR=/data

CMD ["python", "src/app/app.py"]
