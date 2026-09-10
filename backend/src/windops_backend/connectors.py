from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sqlite3
import ssl
import sys
from collections.abc import AsyncIterator, Iterable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SignalMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=512)
    turbine_id: str = Field(min_length=3, max_length=32)
    variable: str = Field(min_length=2, max_length=96)
    unit: str = Field(min_length=1, max_length=24)
    value_field: str = Field(default="value", min_length=1, max_length=96)
    observed_at_field: str = Field(default="observed_at", min_length=1, max_length=96)
    sequence_field: str = Field(default="sequence", min_length=1, max_length=96)
    event_id_field: str = Field(default="source_event_id", min_length=1, max_length=96)
    quality_field: str = Field(default="quality", min_length=1, max_length=96)
    quality_code_field: str = Field(default="quality_code", min_length=1, max_length=96)


class ConnectorConfig(BaseModel):
    """Secret-free, deployable edge connector configuration."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=3, max_length=96)
    transport: Literal["opcua", "mqtt", "http"]
    backend_base_url: str
    backend_api_key_env: str = Field(min_length=1, max_length=128)
    upstream_url: str
    upstream_username_env: str | None = None
    upstream_password_env: str | None = None
    upstream_bearer_token_env: str | None = None
    tls_ca_file: str | None = None
    tls_certificate_file: str | None = None
    tls_private_key_file: str | None = None
    opcua_security_string: str | None = None
    mqtt_topic: str | None = None
    mqtt_qos: Literal[0, 1, 2] = 1
    poll_interval_seconds: float = Field(default=5, ge=0.1, le=3600)
    request_timeout_seconds: float = Field(default=15, ge=1, le=60)
    batch_size: int = Field(default=500, ge=1, le=1000)
    max_delivery_attempts: int = Field(default=20, ge=1, le=1000)
    spool_path: str = Field(min_length=1, max_length=1024)
    mappings: list[SignalMapping] = Field(min_length=1, max_length=10_000)
    allow_insecure_for_test: bool = False

    @model_validator(mode="after")
    def validate_transport(self) -> ConnectorConfig:
        backend = urlparse(self.backend_base_url)
        upstream = urlparse(self.upstream_url)
        if not self.allow_insecure_for_test and backend.scheme != "https":
            raise ValueError("connector backend_base_url must use HTTPS")
        if self.transport == "opcua" and upstream.scheme not in {"opc.tcp", "https"}:
            raise ValueError("OPC UA upstream_url must use opc.tcp or HTTPS")
        if (
            self.transport == "opcua"
            and not self.allow_insecure_for_test
            and (
                not self.opcua_security_string or "SignAndEncrypt" not in self.opcua_security_string
            )
        ):
            raise ValueError("production OPC UA requires a SignAndEncrypt security policy")
        if self.transport == "mqtt":
            if upstream.scheme not in {"mqtts", "wss"} and not self.allow_insecure_for_test:
                raise ValueError("production MQTT upstream_url must use mqtts or wss")
            if not self.mqtt_topic:
                raise ValueError("MQTT connectors require mqtt_topic")
        if (
            self.transport == "http"
            and upstream.scheme != "https"
            and not self.allow_insecure_for_test
        ):
            raise ValueError("production HTTP upstream_url must use HTTPS")
        if len({mapping.key for mapping in self.mappings}) != len(self.mappings):
            raise ValueError("connector mapping keys must be unique")
        spool = Path(self.spool_path).expanduser()
        if spool.name in {"", ".", ".."}:
            raise ValueError("connector spool_path must name a SQLite file")
        return self


class EdgeObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_event_id: str | None = Field(default=None, max_length=128)
    source_sequence: int | None = Field(default=None, ge=0)
    turbine_id: str
    observed_at: datetime
    variable: str
    value: float = Field(allow_inf_nan=False)
    unit: str
    quality: Literal["good", "uncertain", "bad"] = "good"
    quality_code: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


def _quality(value: object) -> Literal["good", "uncertain", "bad"]:
    normalized = str(value or "good").strip().lower()
    if normalized in {"good", "ok", "valid", "0"}:
        return "good"
    if normalized in {"uncertain", "warning", "suspect", "1"}:
        return "uncertain"
    return "bad"


def normalize_observation(
    mapping: SignalMapping,
    raw: Mapping[str, Any] | float | int,
    *,
    received_at: datetime | None = None,
) -> EdgeObservation:
    body: Mapping[str, Any] = raw if isinstance(raw, Mapping) else {"value": raw}
    observed_raw = body.get(mapping.observed_at_field)
    observed_at = (
        datetime.fromisoformat(str(observed_raw).replace("Z", "+00:00"))
        if observed_raw
        else received_at or _utcnow()
    )
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("upstream observation timestamps must include an explicit timezone")
    sequence_raw = body.get(mapping.sequence_field)
    sequence = int(sequence_raw) if sequence_raw is not None else None
    event_raw = body.get(mapping.event_id_field)
    quality_code_raw = body.get(mapping.quality_code_field)
    reserved = {
        mapping.value_field,
        mapping.observed_at_field,
        mapping.sequence_field,
        mapping.event_id_field,
        mapping.quality_field,
        mapping.quality_code_field,
    }
    return EdgeObservation(
        source_event_id=str(event_raw).strip() if event_raw else None,
        source_sequence=sequence,
        turbine_id=mapping.turbine_id,
        observed_at=observed_at.astimezone(UTC),
        variable=mapping.variable,
        value=float(body[mapping.value_field]),
        unit=mapping.unit,
        quality=_quality(body.get(mapping.quality_field)),
        quality_code=str(quality_code_raw).strip() if quality_code_raw else None,
        attributes={str(key): value for key, value in body.items() if key not in reserved},
    )


class TelemetrySpool:
    """Crash-safe, at-least-once local queue with durable dead-letter retention."""

    def __init__(self, path: str, source_id: str, *, max_attempts: int = 20) -> None:
        self.path = Path(path).expanduser().resolve()
        self.source_id = source_id
        self.max_attempts = max_attempts
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS connector_counters (
                    source_id TEXT PRIMARY KEY,
                    next_sequence INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS connector_observations (
                    source_event_id TEXT PRIMARY KEY,
                    source_sequence INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT NOT NULL,
                    last_error TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_connector_delivery
                    ON connector_observations(status, next_attempt_at, source_sequence);
                """
            )

    def enqueue(self, observation: EdgeObservation) -> tuple[str, bool]:
        now = _utcnow()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if observation.source_event_id:
                existing = connection.execute(
                    "SELECT 1 FROM connector_observations WHERE source_event_id = ?",
                    (observation.source_event_id,),
                ).fetchone()
                if existing is not None:
                    return observation.source_event_id, False
            if observation.source_sequence is None:
                row = connection.execute(
                    "SELECT next_sequence FROM connector_counters WHERE source_id = ?",
                    (self.source_id,),
                ).fetchone()
                sequence = int(row["next_sequence"]) if row is not None else 1
                connection.execute(
                    """
                    INSERT INTO connector_counters(source_id, next_sequence) VALUES (?, ?)
                    ON CONFLICT(source_id) DO UPDATE SET next_sequence = excluded.next_sequence
                    """,
                    (self.source_id, sequence + 1),
                )
            else:
                sequence = observation.source_sequence
            payload = observation.model_copy(update={"source_sequence": sequence})
            event_id = observation.source_event_id
            if not event_id:
                identity = json.dumps(
                    {
                        "source_id": self.source_id,
                        "sequence": sequence,
                        "turbine_id": payload.turbine_id,
                        "variable": payload.variable,
                        "observed_at": payload.observed_at.isoformat(),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
                event_id = f"edge-{hashlib.sha256(identity).hexdigest()[:32]}"
            payload = payload.model_copy(update={"source_event_id": event_id})
            serialized = payload.model_dump_json()
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO connector_observations(
                    source_event_id, source_sequence, payload, next_attempt_at, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (event_id, sequence, serialized, now.isoformat(), now.isoformat()),
            )
            return event_id, cursor.rowcount == 1

    def pending(self, limit: int) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload FROM connector_observations
                WHERE status = 'pending' AND next_attempt_at <= ?
                ORDER BY source_sequence LIMIT ?
                """,
                (_utcnow().isoformat(), limit),
            ).fetchall()
        return [json.loads(str(row["payload"])) for row in rows]

    def acknowledge(self, event_ids: Iterable[str]) -> None:
        values = [(event_id,) for event_id in event_ids]
        if not values:
            return
        with self._connect() as connection:
            connection.executemany(
                "DELETE FROM connector_observations WHERE source_event_id = ?", values
            )

    def fail(self, event_ids: Iterable[str], error: str) -> None:
        now = _utcnow()
        with self._connect() as connection:
            for event_id in event_ids:
                row = connection.execute(
                    "SELECT attempts FROM connector_observations WHERE source_event_id = ?",
                    (event_id,),
                ).fetchone()
                if row is None:
                    continue
                attempts = int(row["attempts"]) + 1
                status = "dead" if attempts >= self.max_attempts else "pending"
                delay = min(300, 2 ** min(attempts, 8))
                connection.execute(
                    """
                    UPDATE connector_observations
                    SET status = ?, attempts = ?, next_attempt_at = ?, last_error = ?
                    WHERE source_event_id = ?
                    """,
                    (
                        status,
                        attempts,
                        (now + timedelta(seconds=delay)).isoformat(),
                        error[:4000],
                        event_id,
                    ),
                )

    def counts(self) -> dict[str, int]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT status, COUNT(*) AS count FROM connector_observations GROUP BY status"
            ).fetchall()
        counts = {"pending": 0, "dead": 0}
        counts.update({str(row["status"]): int(row["count"]) for row in rows})
        return counts


class BackendIngestClient:
    def __init__(
        self,
        config: ConnectorConfig,
        spool: TelemetrySpool,
        api_key: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("backend ingest credential is empty")
        self.config = config
        self.spool = spool
        self.api_key = api_key
        self.transport = transport

    async def flush_once(self) -> int:
        samples = self.spool.pending(self.config.batch_size)
        if not samples:
            return 0
        ids = [str(sample["source_event_id"]) for sample in samples]
        try:
            async with httpx.AsyncClient(
                timeout=self.config.request_timeout_seconds,
                follow_redirects=False,
                transport=self.transport,
            ) as client:
                response = await client.post(
                    f"{self.config.backend_base_url.rstrip('/')}/api/v1/scada/ingest",
                    headers={
                        "accept": "application/json",
                        "authorization": f"Bearer {self.api_key}",
                        "content-type": "application/json",
                    },
                    json={"source_id": self.config.source_id, "samples": samples},
                )
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict) or not isinstance(body.get("results"), list):
                raise RuntimeError("WindOps ingest returned an invalid result contract")
            completed = {
                str(item.get("source_event_id"))
                for item in body["results"]
                if isinstance(item, dict)
                and item.get("disposition") in {"accepted", "duplicate", "quarantined"}
            }
            if completed != set(ids):
                raise RuntimeError("WindOps ingest did not acknowledge the complete batch")
        except Exception as exc:
            self.spool.fail(ids, f"{type(exc).__name__}: {exc}")
            raise
        self.spool.acknowledge(ids)
        return len(ids)


async def _http_observations(
    config: ConnectorConfig, bearer_token: str | None
) -> AsyncIterator[tuple[str, Mapping[str, Any] | float | int]]:
    headers = {"accept": "application/json"}
    if bearer_token:
        headers["authorization"] = f"Bearer {bearer_token}"
    async with httpx.AsyncClient(
        timeout=config.request_timeout_seconds, follow_redirects=False
    ) as client:
        response = await client.get(config.upstream_url, headers=headers)
        response.raise_for_status()
        body = response.json()
    rows = body.get("measurements") if isinstance(body, dict) else body
    if not isinstance(rows, list):
        raise RuntimeError("HTTP telemetry source must return a list or measurements list")
    mappings = {mapping.key: mapping for mapping in config.mappings}
    for row in rows:
        if not isinstance(row, dict):
            raise RuntimeError("HTTP telemetry measurements must be JSON objects")
        key = str(row.get("key", ""))
        if key not in mappings:
            raise RuntimeError(f"HTTP telemetry route {key!r} is not governed")
        yield key, row


async def _mqtt_observations(
    config: ConnectorConfig, username: str | None, password: str | None
) -> AsyncIterator[tuple[str, Mapping[str, Any] | float | int]]:
    import aiomqtt

    endpoint = urlparse(config.upstream_url)
    hostname = endpoint.hostname
    topic = config.mqtt_topic
    if hostname is None or topic is None:  # pragma: no cover - validated configuration
        raise RuntimeError("MQTT hostname and topic are required")
    tls_context = ssl.create_default_context(cafile=config.tls_ca_file)
    if config.tls_certificate_file:
        tls_context.load_cert_chain(
            config.tls_certificate_file, keyfile=config.tls_private_key_file
        )
    async with aiomqtt.Client(
        hostname=hostname,
        port=endpoint.port or 8883,
        username=username,
        password=password,
        tls_context=tls_context,
        transport="websockets" if endpoint.scheme == "wss" else "tcp",
    ) as client:
        await client.subscribe(topic, qos=config.mqtt_qos)
        async for message in client.messages:
            row = json.loads(bytes(message.payload).decode("utf-8"))
            if not isinstance(row, dict):
                raise RuntimeError("MQTT telemetry messages must be JSON objects")
            yield str(row.get("key", message.topic)), row


async def _opcua_observations(
    config: ConnectorConfig, username: str | None, password: str | None
) -> AsyncIterator[tuple[str, Mapping[str, Any] | float | int]]:
    from asyncua.client.client import Client

    client = Client(config.upstream_url, timeout=config.request_timeout_seconds)
    if username:
        client.set_user(username)
    if password:
        client.set_password(password)
    if config.opcua_security_string:
        await client.set_security_string(config.opcua_security_string)
    async with client:
        while True:
            for mapping in config.mappings:
                data_value = await client.get_node(mapping.key).read_data_value()
                observed_at = data_value.SourceTimestamp or data_value.ServerTimestamp or _utcnow()
                variant = data_value.Value
                status = data_value.StatusCode
                if variant is None or status is None:
                    raise RuntimeError(f"OPC UA node {mapping.key} returned no value or status")
                status_code = str(status)
                yield (
                    mapping.key,
                    {
                        "value": variant.Value,
                        "observed_at": observed_at.isoformat(),
                        "quality": "good" if status.is_good() else "bad",
                        "quality_code": status_code,
                    },
                )
            await asyncio.sleep(config.poll_interval_seconds)


def _secret(name: str | None, *, required: bool = False) -> str | None:
    value = os.environ.get(name, "").strip() if name else ""
    if required and not value:
        raise RuntimeError(f"required connector secret environment variable {name!r} is empty")
    return value or None


async def run_connector(config: ConnectorConfig) -> None:
    spool = TelemetrySpool(
        config.spool_path,
        config.source_id,
        max_attempts=config.max_delivery_attempts,
    )
    backend_key = _secret(config.backend_api_key_env, required=True)
    if backend_key is None:
        raise RuntimeError("the configured backend API key is unavailable")
    ingest = BackendIngestClient(config, spool, backend_key)
    username = _secret(config.upstream_username_env)
    password = _secret(config.upstream_password_env)
    bearer_token = _secret(config.upstream_bearer_token_env)
    mappings = {mapping.key: mapping for mapping in config.mappings}

    async def flush_forever() -> None:
        while True:
            try:
                await ingest.flush_once()
            except Exception:
                await asyncio.sleep(2)
            else:
                await asyncio.sleep(0.2)

    flusher = asyncio.create_task(flush_forever())
    try:
        while True:
            if config.transport == "http":
                stream = _http_observations(config, bearer_token)
            elif config.transport == "mqtt":
                stream = _mqtt_observations(config, username, password)
            else:
                stream = _opcua_observations(config, username, password)
            try:
                async for key, raw in stream:
                    mapping = mappings.get(key)
                    if mapping is None:
                        raise RuntimeError(f"upstream telemetry route {key!r} is not governed")
                    spool.enqueue(normalize_observation(mapping, raw))
            except Exception:
                await asyncio.sleep(2)
            if config.transport == "http":
                await asyncio.sleep(config.poll_interval_seconds)
    finally:
        flusher.cancel()
        await asyncio.gather(flusher, return_exceptions=True)


def _load_config(path: Path) -> ConnectorConfig:
    with path.open("r", encoding="utf-8") as handle:
        return ConnectorConfig.model_validate(json.load(handle))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a durable WindOps telemetry connector")
    parser.add_argument("--config", type=Path, required=True)
    arguments = parser.parse_args()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_connector(_load_config(arguments.config.resolve())))
