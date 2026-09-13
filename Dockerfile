FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1


RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg tini gosu espeak-ng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

RUN mkdir -p /data/tts-cache /music /config/voices /config/imaging \
    && chmod +x /app/docker-entrypoint.sh

EXPOSE 8095
VOLUME ["/data", "/music", "/config"]

ENTRYPOINT ["/usr/bin/tini", "--", "/app/docker-entrypoint.sh"]
CMD ["gunicorn", "--workers", "1", "--threads", "12", "--timeout", "0", "--bind", "0.0.0.0:8095", "server:app"]
