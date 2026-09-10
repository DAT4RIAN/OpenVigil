import re
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Literal, cast
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from windops_backend.enums import Environment


class TelemetryVariablePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=2, max_length=160)
    unit: str = Field(min_length=1, max_length=24)
    precision: int = Field(default=2, ge=0, le=6)
    normal_min: float
    normal_max: float
    threshold_direction: Literal["above", "below"] = "above"
    warning_threshold: float | None = None
    critical_threshold: float | None = None

    @model_validator(mode="after")
    def validate_ranges(self) -> "TelemetryVariablePolicy":
        if self.normal_min >= self.normal_max:
            raise ValueError("telemetry normal_min must be below normal_max")
        thresholds = [
            value
            for value in (self.warning_threshold, self.critical_threshold)
            if value is not None
        ]
        if self.threshold_direction == "above" and thresholds != sorted(thresholds):
            raise ValueError("above thresholds must be ordered warning then critical")
        if self.threshold_direction == "below" and thresholds != sorted(thresholds, reverse=True):
            raise ValueError("below thresholds must be ordered warning then critical")
        return self


class TelemetrySourcePolicy(BaseModel):
    """Governed normalization and ordering policy for one external data source."""

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=3, max_length=160)
    source_kind: Literal["opcua", "mqtt", "iec61400_25", "cms", "weather", "rest"]
    enabled: bool = True
    sequence_required: bool = True
    max_lateness_seconds: int = Field(default=300, ge=0, le=86_400)
    max_future_skew_seconds: int = Field(default=120, ge=0, le=3_600)
    expected_heartbeat_seconds: int = Field(default=60, ge=5, le=86_400)
    allowed_turbines: list[str] = Field(default_factory=list, max_length=10_000)
    allowed_variables: list[str] = Field(default_factory=list, max_length=10_000)
    variable_contracts: dict[str, TelemetryVariablePolicy] = Field(default_factory=dict)


class IdentityAccessScope(BaseModel):
    """Server-owned asset and data grants for one Sites identity.

    Roles answer *what* a user may do.  These grants answer *which data* that
    role may see.  The gateway only signs the subject; scope values remain
    backend configuration so a caller cannot enlarge its own visibility by
    adding claims or query parameters.
    """

    model_config = ConfigDict(extra="forbid")

    tenant_ids: list[str] = Field(default_factory=list, max_length=10_000)
    wind_farm_ids: list[str] = Field(default_factory=list, max_length=10_000)
    turbine_ids: list[str] = Field(default_factory=list, max_length=50_000)
    entity_ids: list[str] = Field(default_factory=list, max_length=50_000)
    data_scopes: list[str] = Field(default_factory=list, max_length=256)
    allow_global: bool = False

    @model_validator(mode="after")
    def validate_scope_values(self) -> "IdentityAccessScope":
        fields = {
            "tenant_ids": self.tenant_ids,
            "wind_farm_ids": self.wind_farm_ids,
            "turbine_ids": self.turbine_ids,
            "entity_ids": self.entity_ids,
            "data_scopes": self.data_scopes,
        }
        for name, values in fields.items():
            if any(not value.strip() for value in values):
                raise ValueError(f"identity access scope {name} cannot contain empty values")
            normalized = [value.strip().casefold() for value in values]
            if len(values) != len(set(normalized)):
                raise ValueError(f"identity access scope {name} cannot contain duplicates")
            setattr(self, name, [value.strip() for value in values])
        return self


class ModelInferenceTarget(BaseModel):
    """Secret-bearing, operator-managed route to an external inference service."""

    model_config = ConfigDict(extra="forbid")

    endpoint_url: str
    api_token: SecretStr
    # The predictive request contract reserves time for the backend batch and
    # gateway after the single-target call completes: 15s < 25s < 30s.
    timeout_seconds: int = Field(default=15, ge=1, le=20)


class Settings(BaseSettings):
    """Runtime configuration with a hard production/test storage boundary."""

    model_config = SettingsConfigDict(
        # Runtime entrypoints load the repository-local dotenv file explicitly
        # through get_settings().  Direct Settings(...) construction must stay
        # deterministic for tests and tools that provide their own values.
        env_file=None,
        env_prefix="WINDOPS_",
        case_sensitive=False,
        extra="ignore",
    )

    environment: Environment = Environment.DEVELOPMENT
    database_url: str = "postgresql+asyncpg://windops:windops@localhost:5432/windops"
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "windops"
    minio_secret_key: SecretStr = SecretStr("windops-development-only")
    minio_secure: bool = False
    minio_public_base: str = "http://localhost:9000"
    minio_field_evidence_bucket: str = "windops-field-evidence"
    minio_knowledge_bucket: str = "windops-knowledge-documents"
    minio_model_bucket: str = "windops-model-artifacts"
    minio_twin_bucket: str = "windops-twin-artifacts"
    minio_care_bucket: str = "windops-care-benchmarks"
    minio_care_raw_prefix: str = "care/v6/raw"
    minio_care_standard_prefix: str = "care/v6/standard"
    minio_care_quality_prefix: str = "care/v6/quality"
    minio_care_predictions_prefix: str = "care/v6/predictions"
    minio_care_reports_prefix: str = "care/v6/reports"
    model_inference_targets: dict[str, ModelInferenceTarget] = Field(default_factory=dict)
    agent_mode: Literal["deterministic", "litellm"] = "deterministic"
    litellm_model: str = "openai/gpt-5-mini"
    litellm_timeout_seconds: int = Field(default=45, ge=5, le=120)
    litellm_max_retries: int = Field(default=2, ge=0, le=5)
    litellm_minimum_diagnosis_confidence: float = Field(default=0.5, ge=0, le=1)
    otel_enabled: bool = False
    otel_service_name: str = "windops-backend"
    otel_exporter_otlp_endpoint: str = ""
    otel_exporter_otlp_headers: dict[str, SecretStr] = Field(default_factory=dict)
    metrics_bearer_token: SecretStr = SecretStr("dev-metrics-token-replace-before-use")
    slo_http_availability_target: float = Field(default=0.999, gt=0, le=1)
    slo_http_p95_latency_seconds: float = Field(default=2.0, gt=0, le=60)
    slo_agent_success_target: float = Field(default=0.99, gt=0, le=1)
    slo_telemetry_freshness_seconds: int = Field(default=120, ge=10, le=86_400)
    embedding_model: str = "text-embedding-3-small"
    embedding_timeout_seconds: int = Field(default=20, ge=1, le=120)
    embedding_batch_size: int = Field(default=16, ge=1, le=128)
    embedding_max_retries: int = Field(default=2, ge=0, le=5)
    knowledge_graph_backend: Literal["memory", "neo4j"] = "neo4j"
    neo4j_uri: str = "neo4j://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("windops-neo4j-development-only")
    neo4j_database: str = "neo4j"
    knowledge_graph_rebuild_on_startup: bool = False
    knowledge_graph_projection_batch_size: int = Field(default=500, ge=50, le=5_000)
    knowledge_graph_projection_max_source_rows: int = Field(default=250_000, ge=1_000, le=5_000_000)
    knowledge_graph_projection_max_nodes: int = Field(default=250_000, ge=1_000, le=5_000_000)
    knowledge_graph_projection_max_relationships: int = Field(
        default=500_000, ge=1_000, le=10_000_000
    )
    knowledge_graph_projection_max_source_megabytes: int = Field(default=512, ge=64, le=8_192)
    knowledge_graph_projection_max_graph_megabytes: int = Field(default=256, ge=64, le=4_096)
    knowledge_graph_projection_max_memory_megabytes: int = Field(default=256, ge=64, le=4_096)
    knowledge_graph_projection_max_runtime_seconds: int = Field(default=300, ge=30, le=3_600)
    schema_bootstrap: bool = False
    demo_seed: bool = False
    # Tests must opt into synchronous draining. Non-test runtimes always dispatch
    # durable outbox events through Dramatiq/Redis.
    outbox_inline_drain: bool = False
    # Business reads append a minimized event to this durable Redis stream before
    # executing. A separate worker commits bounded batches to monthly PostgreSQL
    # partitions; maintenance compresses hot rows before final retention expiry.
    read_audit_stream_key: str = "windops:read-audit:v2"
    read_audit_consumer_group: str = "windops-read-audit-writers-v2"
    read_audit_stream_max_pending: int = Field(default=100_000, ge=1_000, le=10_000_000)
    read_audit_enqueue_timeout_ms: int = Field(default=250, ge=25, le=2_000)
    read_audit_batch_size: int = Field(default=500, ge=10, le=5_000)
    read_audit_worker_block_ms: int = Field(default=2_000, ge=100, le=30_000)
    read_audit_reclaim_idle_ms: int = Field(default=60_000, ge=5_000, le=3_600_000)
    read_audit_archive_after_days: int = Field(default=30, ge=1, le=365)
    read_audit_retention_days: int = Field(default=365, ge=30, le=3_650)
    read_audit_maintenance_batch_size: int = Field(default=10_000, ge=100, le=100_000)
    read_audit_partition_months_ahead: int = Field(default=3, ge=1, le=24)
    api_prefix: str = "/api/v1"
    bind_host: str = "127.0.0.1"
    release_id: str = "development"
    release_commit_sha: str = ""
    release_image_digest: str = ""
    docs_enabled: bool = True
    trusted_hosts: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "test", "testserver"]
    )
    max_request_body_bytes: int = Field(default=2 * 1024 * 1024, ge=1024, le=32 * 1024 * 1024)
    rate_limit_enabled: bool = False
    rate_limit_requests_per_minute: int = Field(default=600, ge=10, le=100_000)
    rate_limit_client_requests_per_minute: int = Field(default=10_000, ge=100, le=1_000_000)
    test_auth_bypass_enabled: bool = False
    auth_mode: Literal["static_tokens", "sites_delegation"] = "static_tokens"
    gateway_delegation_secret: SecretStr = SecretStr("dev-delegation-secret-replace")
    gateway_delegation_previous_secret: SecretStr = SecretStr("")
    gateway_delegation_issuer: Literal["windops-sites-gateway"] = "windops-sites-gateway"
    gateway_delegation_audience: Literal["windops-python-backend"] = "windops-python-backend"
    identity_role_mappings: dict[str, list[str]] = Field(default_factory=dict)
    identity_scope_mappings: dict[str, IdentityAccessScope] = Field(default_factory=dict)
    delegation_clock_skew_seconds: int = Field(default=15, ge=0, le=120)
    # The legacy shared key is development-only. Production authenticates every
    # external source with a distinct credential and a matching governed policy.
    scada_ingest_api_key: SecretStr = SecretStr("dev-scada-key-replace-before-use-0001")
    ingest_source_api_keys: dict[str, SecretStr] = Field(default_factory=dict)
    telemetry_source_policies: dict[str, TelemetrySourcePolicy] = Field(default_factory=dict)
    event_stream_poll_milliseconds: int = Field(default=1_000, ge=100, le=10_000)
    event_stream_connection_seconds: int = Field(default=25, ge=5, le=25)
    eam_enabled: bool = False
    eam_base_url: str = ""
    eam_api_token: SecretStr = SecretStr("")
    eam_webhook_api_key: SecretStr = SecretStr("")
    eam_timeout_seconds: int = Field(default=10, ge=1, le=30)
    operations_approver_api_key: SecretStr = SecretStr("dev-approver-key-replace-before-use-01")
    maintenance_reviewer_api_key: SecretStr = SecretStr("dev-reviewer-key-replace-before-use-01")
    operations_manager_api_key: SecretStr = SecretStr("dev-manager-key-replace-before-use-001")
    field_technician_api_key: SecretStr = SecretStr("dev-field-key-replace-before-use-0001")

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite+")

    @model_validator(mode="after")
    def enforce_environment_boundaries(self) -> "Settings":
        care_prefixes = (
            self.minio_care_raw_prefix,
            self.minio_care_standard_prefix,
            self.minio_care_quality_prefix,
            self.minio_care_predictions_prefix,
            self.minio_care_reports_prefix,
        )
        if not self.minio_care_bucket.strip():
            raise ValueError("CARE benchmark object-storage bucket cannot be empty")
        operational_buckets = {
            self.minio_field_evidence_bucket,
            self.minio_knowledge_bucket,
            self.minio_model_bucket,
            self.minio_twin_bucket,
        }
        if self.minio_care_bucket in operational_buckets:
            raise ValueError("CARE benchmark object-storage bucket must be operationally isolated")
        if len(set(care_prefixes)) != len(care_prefixes) or any(
            not prefix.startswith("care/v6/")
            or PurePosixPath(prefix).is_absolute()
            or ".." in PurePosixPath(prefix).parts
            or "\\" in prefix
            or "//" in prefix
            or str(PurePosixPath(prefix)) != prefix
            for prefix in care_prefixes
        ):
            raise ValueError("CARE benchmark object-storage prefixes must be distinct and safe")
        if self.is_sqlite and self.environment is not Environment.TEST:
            raise ValueError("SQLite is test-only; development and production require PostgreSQL")
        if self.test_auth_bypass_enabled and self.environment is not Environment.TEST:
            raise ValueError("the test authentication bypass is test-only")
        if self.outbox_inline_drain and self.environment is not Environment.TEST:
            raise ValueError("inline outbox draining is test-only")
        if self.read_audit_archive_after_days >= self.read_audit_retention_days:
            raise ValueError("read audit archive age must be below final retention")
        if self.read_audit_stream_max_pending < self.read_audit_batch_size * 2:
            raise ValueError("read audit stream capacity must hold at least two worker batches")
        for value in (self.read_audit_stream_key, self.read_audit_consumer_group):
            if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9:._-]{2,127}", value) is None:
                raise ValueError("read audit Redis names must be bounded safe identifiers")
        if self.knowledge_graph_backend == "memory" and self.environment is not Environment.TEST:
            raise ValueError("the in-memory knowledge graph is test-only")
        if self.environment is Environment.PRODUCTION:
            if not self.database_url.startswith("postgresql+asyncpg://"):
                raise ValueError("production requires postgresql+asyncpg")
            if self.schema_bootstrap:
                raise ValueError("production schema changes must be applied with Alembic")
            if self.demo_seed:
                raise ValueError("production cannot enable demo seeding")
            if self.agent_mode != "litellm":
                raise ValueError("production requires the LiteLLM reasoning provider")
            if (
                re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,127}", self.release_id) is None
                or self.release_id.lower() in {"development", "unknown", "unreleased"}
                or "replace" in self.release_id.lower()
            ):
                raise ValueError("production requires an immutable release ID")
            if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", self.release_commit_sha) is None:
                raise ValueError("production requires a full lowercase Git commit SHA")
            if (
                re.fullmatch(r"sha256:[0-9a-f]{64}", self.release_image_digest) is None
                or self.release_image_digest == "sha256:" + "0" * 64
            ):
                raise ValueError("production requires a non-placeholder image SHA-256 digest")
            if not self.litellm_model.strip():
                raise ValueError("production requires an explicit LiteLLM reasoning model")
            if not self.embedding_model.strip():
                raise ValueError("production requires an explicit embedding model")
            if not self.otel_enabled:
                raise ValueError("production requires OpenTelemetry export")
            if not self.otel_service_name.strip():
                raise ValueError("production requires an OpenTelemetry service name")
            if not self.trusted_hosts or any(
                not host.strip()
                or host == "*"
                or "://" in host
                or "/" in host
                or host.lower() in {"localhost", "127.0.0.1", "::1", "test", "testserver"}
                for host in self.trusted_hosts
            ):
                raise ValueError("production requires explicit non-development trusted Host names")
            if (
                not self.bind_host.strip()
                or "://" in self.bind_host
                or "/" in self.bind_host
                or self.bind_host.lower() in {"localhost", "127.0.0.1", "::1"}
            ):
                raise ValueError("production API must bind to a non-loopback host or IP address")
            if self.docs_enabled:
                raise ValueError("production OpenAPI documentation must be disabled")
            if not self.rate_limit_enabled:
                raise ValueError("production requires Redis-backed request rate limiting")
            otlp_endpoint = urlparse(self.otel_exporter_otlp_endpoint)
            if (
                otlp_endpoint.scheme != "https"
                or not otlp_endpoint.netloc
                or otlp_endpoint.hostname in {"localhost", "127.0.0.1", "::1"}
                or otlp_endpoint.username
                or otlp_endpoint.password
                or otlp_endpoint.query
                or otlp_endpoint.fragment
            ):
                raise ValueError("production requires an external HTTPS OTLP endpoint")
            metrics_token = self.metrics_bearer_token.get_secret_value()
            if (
                len(metrics_token) < 32
                or metrics_token.startswith("dev-")
                or "replace" in metrics_token.lower()
            ):
                raise ValueError("production requires a strong metrics bearer token")
            if self.knowledge_graph_backend != "neo4j":
                raise ValueError("production requires the Neo4j knowledge graph projection")
            if not self.neo4j_uri.startswith("neo4j+s://"):
                raise ValueError("production Neo4j requires verified TLS (neo4j+s://)")
            neo4j_secret = self.neo4j_password.get_secret_value()
            if (
                not self.neo4j_user.strip()
                or len(neo4j_secret) < 32
                or neo4j_secret.lower()
                in {"", "neo4j", "change-me", "password", "windops-neo4j-development-only"}
            ):
                raise ValueError("production rejects missing or example Neo4j credentials")
            database = urlparse(self.database_url)
            tls_values = parse_qs(database.query).get("ssl", []) + parse_qs(database.query).get(
                "sslmode", []
            )
            if not any(
                value.lower() in {"require", "verify-ca", "verify-full"} for value in tls_values
            ):
                raise ValueError("production PostgreSQL requires TLS (ssl=require or stronger)")
            if (database.password or "").lower() in {"", "windops", "change-me", "password"}:
                raise ValueError("production rejects missing or example PostgreSQL credentials")
            if not self.redis_url.startswith("rediss://"):
                raise ValueError("production Redis requires TLS (rediss://)")
            if not self.minio_endpoint.strip():
                raise ValueError("production requires a MinIO endpoint")
            if not self.minio_field_evidence_bucket.strip():
                raise ValueError("production requires a field-evidence bucket")
            if not self.minio_knowledge_bucket.strip():
                raise ValueError("production requires a knowledge-document bucket")
            if not self.minio_model_bucket.strip():
                raise ValueError("production requires a model-artifact bucket")
            if not self.minio_twin_bucket.strip():
                raise ValueError("production requires a twin-artifact bucket")
            if not self.minio_care_bucket.strip():
                raise ValueError("production requires a CARE benchmark bucket")
            if not self.minio_secure:
                raise ValueError("production requires MinIO TLS")
            if self.auth_mode != "sites_delegation":
                raise ValueError("production requires Sites per-user delegated authentication")
            delegation_secret = self.gateway_delegation_secret.get_secret_value()
            if (
                len(delegation_secret) < 48
                or delegation_secret.startswith("dev-")
                or "replace" in delegation_secret.lower()
            ):
                raise ValueError("production requires an external gateway delegation secret")
            previous_delegation_secret = self.gateway_delegation_previous_secret.get_secret_value()
            if previous_delegation_secret and (
                len(previous_delegation_secret) < 48
                or previous_delegation_secret == delegation_secret
            ):
                raise ValueError(
                    "previous delegation secret must be distinct and at least 48 characters"
                )
            # Under auth_mode="sites_delegation" the API never registers the four
            # static role keys (see api.get_principal), so the approver,
            # reviewer, and technician keys carry no production authority. The
            # operations-manager key stays security-relevant in every
            # environment because it authenticates the windops-reference-import
            # CLI, so production must not keep its published development value.
            manager_key = self.operations_manager_api_key.get_secret_value()
            if (
                len(manager_key) < 32
                or manager_key.startswith("dev-")
                or "replace" in manager_key.lower()
            ):
                raise ValueError("production requires a strong operations-manager API key")
            if (
                not self.gateway_delegation_issuer.strip()
                or not self.gateway_delegation_audience.strip()
            ):
                raise ValueError("production requires delegation issuer and audience values")
            required_human_roles = {
                "operations_manager",
                "operations_approver",
                "maintenance_reviewer",
                "field_technician",
            }
            assigned_roles = {
                role for roles in self.identity_role_mappings.values() for role in roles
            }
            if not required_human_roles.issubset(assigned_roles):
                raise ValueError("production identity mappings must cover every human role")
            if any(
                not subject.strip() or not roles
                for subject, roles in self.identity_role_mappings.items()
            ):
                raise ValueError("production identity mappings cannot contain empty assignments")
            human_subjects = {
                subject
                for subject, roles in self.identity_role_mappings.items()
                if required_human_roles.intersection(roles)
            }
            missing_scopes = sorted(
                subject for subject in human_subjects if subject not in self.identity_scope_mappings
            )
            if missing_scopes:
                raise ValueError(
                    "production human identities require explicit access scopes: "
                    + ", ".join(missing_scopes)
                )
            empty_scopes = sorted(
                subject
                for subject in human_subjects
                if not (
                    self.identity_scope_mappings[subject].tenant_ids
                    or self.identity_scope_mappings[subject].wind_farm_ids
                    or self.identity_scope_mappings[subject].turbine_ids
                    or self.identity_scope_mappings[subject].entity_ids
                    or self.identity_scope_mappings[subject].allow_global
                )
            )
            if empty_scopes:
                raise ValueError(
                    "production human identities require a tenant, asset, entity, or global grant: "
                    + ", ".join(empty_scopes)
                )
            public_minio = urlparse(self.minio_public_base)
            if (
                public_minio.scheme != "https"
                or not public_minio.netloc
                or public_minio.hostname in {"localhost", "127.0.0.1", "::1"}
                or public_minio.path not in {"", "/"}
                or public_minio.query
                or public_minio.fragment
            ):
                raise ValueError("production requires an external HTTPS MinIO public base")
            minio_secret = self.minio_secret_key.get_secret_value()
            if (
                self.minio_access_key.lower() in {"", "windops", "minioadmin", "change-me"}
                or len(minio_secret) < 32
                or minio_secret.lower()
                in {"", "windops-development-only", "minioadmin", "change-me"}
            ):
                raise ValueError("production rejects missing or example MinIO credentials")
            source_ids = set(self.telemetry_source_policies)
            if not source_ids or source_ids != set(self.ingest_source_api_keys):
                raise ValueError(
                    "production requires one distinct credential for every telemetry source policy"
                )
            if any(
                not source_id.strip()
                or len(source_id) > 96
                or not source_id.replace("-", "").replace("_", "").isalnum()
                for source_id in source_ids
            ):
                raise ValueError("telemetry source IDs must be portable identifiers")
            if any(not policy.enabled for policy in self.telemetry_source_policies.values()):
                raise ValueError(
                    "disabled telemetry sources must be removed from production config"
                )
            if any(
                not policy.allowed_turbines or not policy.variable_contracts
                for policy in self.telemetry_source_policies.values()
            ):
                raise ValueError(
                    "production telemetry sources require turbine scopes and variable contracts"
                )
            if any(
                policy.allowed_variables
                and set(policy.allowed_variables) != set(policy.variable_contracts)
                for policy in self.telemetry_source_policies.values()
            ):
                raise ValueError(
                    "allowed_variables must match variable_contracts when both are configured"
                )
            governed_routes: set[tuple[str, str]] = set()
            for policy in self.telemetry_source_policies.values():
                routes = {
                    (turbine_id, variable)
                    for turbine_id in policy.allowed_turbines
                    for variable in policy.variable_contracts
                }
                if governed_routes.intersection(routes):
                    raise ValueError(
                        "a production turbine-variable route can belong to only one source"
                    )
                governed_routes.update(routes)
            keys = [secret.get_secret_value() for secret in self.ingest_source_api_keys.values()]
            rejected = {"", "windops", "change-me", "password"}
            if any(
                len(value) < 32
                or value.lower() in rejected
                or value.startswith("dev-")
                or "replace-before-use" in value.lower()
                for value in keys
            ):
                raise ValueError("production requires a non-example secret per telemetry source")
            if len(set(keys)) != len(keys):
                raise ValueError("production telemetry source credentials must be distinct")
            if not self.eam_enabled:
                raise ValueError("production requires the governed EAM work-order integration")
            eam_url = urlparse(self.eam_base_url)
            if (
                eam_url.scheme != "https"
                or not eam_url.netloc
                or eam_url.hostname in {"localhost", "127.0.0.1", "::1"}
                or eam_url.query
                or eam_url.fragment
            ):
                raise ValueError("production EAM integration requires an external HTTPS base URL")
            eam_secrets = [
                self.eam_api_token.get_secret_value(),
                self.eam_webhook_api_key.get_secret_value(),
            ]
            if any(
                len(value) < 32
                or value.lower() in rejected
                or value.startswith("dev-")
                or "replace" in value.lower()
                for value in eam_secrets
            ):
                raise ValueError("production requires independent non-example EAM credentials")
            if len(set(eam_secrets)) != 2:
                raise ValueError("EAM outbound and inbound credentials must be distinct")
            if not self.model_inference_targets:
                raise ValueError("production requires at least one governed model inference target")
            inference_tokens: list[str] = []
            for target_id, target in self.model_inference_targets.items():
                target_url = urlparse(target.endpoint_url)
                if (
                    not target_id.strip()
                    or len(target_id) > 96
                    or not target_id.replace("-", "").replace("_", "").isalnum()
                ):
                    raise ValueError("model inference target IDs must be portable identifiers")
                if (
                    target_url.scheme != "https"
                    or not target_url.netloc
                    or target_url.hostname in {"localhost", "127.0.0.1", "::1"}
                    or target_url.username
                    or target_url.password
                    or target_url.query
                    or target_url.fragment
                ):
                    raise ValueError(
                        "production model inference targets require external HTTPS endpoints"
                    )
                token = target.api_token.get_secret_value()
                if (
                    len(token) < 32
                    or token.lower() in rejected
                    or token.startswith("dev-")
                    or "replace" in token.lower()
                ):
                    raise ValueError("production model inference targets require strong secrets")
                inference_tokens.append(token)
            if len(set(inference_tokens)) != len(inference_tokens):
                raise ValueError("model inference targets require distinct credentials")
        if self.environment is Environment.TEST and not self.is_sqlite:
            # PostgreSQL integration tests remain valid; this only prevents accidental test
            # configuration from being represented as production configuration.
            return self
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    local_env_file = Path(__file__).resolve().parents[2] / ".env"
    # pydantic-settings supplies underscore-prefixed source controls at runtime;
    # its mypy plugin intentionally exposes only declared model fields.
    settings_factory = cast(Callable[..., Settings], Settings)
    return settings_factory(_env_file=local_env_file)
