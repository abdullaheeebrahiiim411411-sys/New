FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends gnupg ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY render-shell/requirements.txt /tmp/requirements.txt
RUN python -m pip install --disable-pip-version-check --no-cache-dir -r /tmp/requirements.txt \
    && rm -f /tmp/requirements.txt
COPY . /app
RUN chmod 0755 /app/start.sh

EXPOSE 10000
CMD ["/app/start.sh"]
