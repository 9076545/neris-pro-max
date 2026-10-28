FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    NERIS_ADMIN_BIND_HOST=0.0.0.0 \
    NERIS_ADMIN_PORT=8000

WORKDIR /app
RUN apt-get update \
    && apt-get install --no-install-recommends -y git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY agents ./agents
COPY connectors ./connectors
COPY core ./core
COPY hud ./hud
COPY neris_agentes ./neris_agentes
COPY supabase ./supabase

EXPOSE 10000
CMD ["sh", "-c", "uvicorn hud.server:app --host 0.0.0.0 --port ${PORT:-10000}"]
