FROM python:3.11-slim

# Tools: curl, unzip (gradle wrapper needs), OpenJDK, Maven, Postgres headers
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl unzip ca-certificates build-essential libpq-dev \
    openjdk-21-jdk-headless maven \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8080
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8080","--proxy-headers"]

# Canonical status guard
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
COPY sitecustomize.py /app/sitecustomize.py
