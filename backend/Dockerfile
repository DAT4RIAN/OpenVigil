# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e

ARG PYTHON_BASE_IMAGE=python:3.12.11-slim-trixie@sha256:0000000000000000000000000000000000000000000000000000000000000000
ARG POSTGRES_CLIENT_IMAGE=timescale/timescaledb-ha@sha256:df8eaa04de65fbe238df8dbc356e79108bcb8166d3458833536a3ff745abb2be
ARG POSTGRES_CLIENT_MAJOR=16

FROM ${POSTGRES_CLIENT_IMAGE} AS postgres-client

FROM ${PYTHON_BASE_IMAGE} AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build
COPY pyproject.toml README.md requirements.container.txt ./
COPY src ./src
RUN python -m pip wheel --require-hashes --wheel-dir /wheels -r requirements.container.txt \
    && python -m pip wheel --no-deps --wheel-dir /wheels .

FROM ${PYTHON_BASE_IMAGE} AS runtime

ARG WINDOPS_RELEASE_ID=unreleased
ARG WINDOPS_COMMIT_SHA=unknown
ARG WINDOPS_SOURCE_URL=unknown
ARG PYTHON_BASE_IMAGE
ARG POSTGRES_CLIENT_IMAGE
ARG POSTGRES_CLIENT_MAJOR
LABEL org.opencontainers.image.title="OpenVigil backend" \
    org.opencontainers.image.version="${WINDOPS_RELEASE_ID}" \
    org.opencontainers.image.revision="${WINDOPS_COMMIT_SHA}" \
    org.opencontainers.image.source="${WINDOPS_SOURCE_URL}" \
    org.opencontainers.image.base.name="${PYTHON_BASE_IMAGE}" \
    org.windops.postgresql-client.image="${POSTGRES_CLIENT_IMAGE}" \
    org.windops.postgresql-client.major="${POSTGRES_CLIENT_MAJOR}"

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# The production TimescaleDB service is PostgreSQL 16. Copy the three client
# entrypoints from that exact immutable image so pg_dump/pg_restore cannot emit
# SQL settings introduced by a newer client (for example transaction_timeout).
COPY --from=postgres-client /usr/lib/postgresql/16/bin/pg_dump /usr/local/bin/pg_dump
COPY --from=postgres-client /usr/lib/postgresql/16/bin/pg_restore /usr/local/bin/pg_restore
COPY --from=postgres-client /usr/lib/postgresql/16/bin/psql /usr/local/bin/psql

COPY --from=builder /wheels /wheels
COPY --from=builder /build/requirements.container.txt /tmp/requirements.container.txt
RUN python -m pip install --no-index --find-links=/wheels --require-hashes -r /tmp/requirements.container.txt \
    && python -m pip install --no-index --find-links=/wheels --no-deps windops-backend \
    && rm -f /tmp/requirements.container.txt \
    && rm -rf /wheels

RUN groupadd --gid 10001 windops \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent windops

WORKDIR /app
COPY alembic.ini requirements.container.txt ./
COPY alembic ./alembic
COPY connector.example.json ./
RUN windops-care-dependency-closure \
    --requirements-lock /app/requirements.container.txt \
    --report /app/care-benchmark-dependency-closure.json
RUN chown -R 10001:10001 /app

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import json,os,urllib.request; host=json.loads(os.environ['WINDOPS_TRUSTED_HOSTS'])[0]; request=urllib.request.Request('http://127.0.0.1:8000/api/v1/healthz',headers={'Host':host}); urllib.request.urlopen(request,timeout=2).read()"]

CMD ["windops-api"]
