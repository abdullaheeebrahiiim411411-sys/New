FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends gnupg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app
RUN python -m pip install --no-cache-dir -r /app/render-shell/requirements.txt \
    && chmod 0755 /app/render-shell/start.sh

EXPOSE 10000
CMD ["/app/render-shell/start.sh"]
