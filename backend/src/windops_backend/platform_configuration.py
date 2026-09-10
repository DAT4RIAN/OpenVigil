from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import unquote, urlparse

from pydantic import BaseModel, ConfigDict, Field, model_validator

ConfigurationKey = Literal[
    "scada_retention",
    "event_stream",
    "identity",
    "model_governance",
    "backup_policy",
]

PLATFORM_CONFIGURATION_SCHEMA_VERSION = 1
MAX_CONFIGURATION_BYTES = 16_384
MAX_CONFIGURATION_DEPTH = 6
MAX_CONFIGURATION_NODES = 256
MAX_CONFIGURATION_KEY_LENGTH = 96

_SECRET_REFERENCE_SCHEMES = frozenset(
    {"vault", "aws-secretsmanager", "azure-keyvault", "gcp-secretmanager"}
)
_SENSITIVE_KEY_MARKERS = (
    "token",
    "secret",
    "password",
    "passwd",
    "passphrase",
    "pwd",
    "privatekey",
    "credential",
    "connectionstring",
    "apikey",
    "accesskey",
    "clientsecret",
    "authorization",
    "bearer",
)
_LABELED_CREDENTIAL = re.compile(
    r"(?i)(?:password|passwd|pwd|token|secret|api[\s_-]*key|credential)"
    r"\s*[:=]\s*[^\s,;&]{6,}"
)
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_KNOWN_SECRET_PREFIX = re.compile(
    r"(?i)^(?:sk-(?:live|prod|test|proj)-|sk_(?:live|test)_|rk_(?:live|test)_|"
    r"gh[opusr]_|xox[abprs]-|AKIA|ASIA|glpat-|pypi-|npm_[A-Za-z0-9_-]{4,}|"
    r"hf_|AIza|ya29\.)[A-Za-z0-9._-]{8,}$"
)
_AUTHORIZATION_CREDENTIAL = re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}")
_CLOUD_CONNECTION_CREDENTIAL = re.compile(
    r"(?i)(?:accountkey|sharedaccesskey|accesskey)\s*=\s*[^\s,;&]{8,}"
)
_OPAQUE_TOKEN_SHAPE = re.compile(r"^[A-Za-z0-9_-]{32,}$")


class PlatformConfigurationValidationError(ValueError):
    """Safe validation error whose message never includes submitted values."""


class _StrictConfigurationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    schema_version: Literal[1] = 1


class ScadaRetentionV1(_StrictConfigurationModel):
    days: int = Field(ge=1, le=3650)
    downsample_after_days: int | None = Field(default=None, ge=1, le=3650)

    @model_validator(mode="after")
    def validate_downsample_window(self) -> ScadaRetentionV1:
        if self.downsample_after_days is not None and self.downsample_after_days > self.days:
            raise ValueError("downsample_after_days cannot exceed days")
        return self


class EventStreamV1(_StrictConfigurationModel):
    transport: Literal["sse", "kafka", "nats"]
    topic: str | None = Field(default=None, min_length=1, max_length=240)
    consumer_group: str | None = Field(default=None, min_length=1, max_length=160)
    max_batch_size: int = Field(default=200, ge=1, le=1000)

    @model_validator(mode="after")
    def validate_external_transport(self) -> EventStreamV1:
        if self.transport in {"kafka", "nats"} and self.topic is None:
            raise ValueError("external event streams require topic")
        if self.transport == "sse" and (self.topic is not None or self.consumer_group is not None):
            raise ValueError("SSE event streams do not accept broker fields")
        return self


class IdentityV1(_StrictConfigurationModel):
    issuer: str = Field(min_length=12, max_length=1024)
    audience: str = Field(min_length=1, max_length=240)
    jwks_cache_seconds: int = Field(default=300, ge=30, le=86_400)

    @model_validator(mode="after")
    def validate_issuer(self) -> IdentityV1:
        parsed = urlparse(self.issuer)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ValueError("issuer must be an HTTPS URL without credentials or fragments")
        return self


class ModelEvaluationPolicyV1(_StrictConfigurationModel):
    minimum_validation_auc: float = Field(ge=0.5, le=1.0)
    minimum_evaluation_samples: int = Field(ge=30, le=10_000_000)
    maximum_regression_percent: float = Field(default=2.0, ge=0, le=100)


class ModelGovernanceV1(_StrictConfigurationModel):
    approval_required: bool
    automatic_rollback: bool = True
    evaluation: ModelEvaluationPolicyV1


class BackupVerificationPolicyV1(_StrictConfigurationModel):
    restore_test_interval_days: int = Field(default=30, ge=1, le=365)
    retention_days: int = Field(default=30, ge=1, le=3650)


class BackupPolicyV1(_StrictConfigurationModel):
    rpo_minutes: int = Field(ge=1, le=1440)
    rto_minutes: int = Field(ge=1, le=10_080)
    verification: BackupVerificationPolicyV1 = Field(default_factory=BackupVerificationPolicyV1)

    @model_validator(mode="after")
    def validate_recovery_targets(self) -> BackupPolicyV1:
        if self.rto_minutes < self.rpo_minutes:
            raise ValueError("rto_minutes cannot be lower than rpo_minutes")
        return self


_SCHEMA_BY_KEY: dict[str, type[_StrictConfigurationModel]] = {
    "scada_retention": ScadaRetentionV1,
    "event_stream": EventStreamV1,
    "identity": IdentityV1,
    "model_governance": ModelGovernanceV1,
    "backup_policy": BackupPolicyV1,
}


@dataclass(frozen=True)
class ConfigurationInspection:
    serialized_size: int
    finding_categories: tuple[str, ...]


def _normalized_key(value: str) -> str:
    expanded_camel_case = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    normalized = unicodedata.normalize("NFKC", expanded_camel_case).casefold()
    return re.sub(r"[^a-z0-9]+", "", normalized)


def _sensitive_key_category(key: str) -> str | None:
    normalized = _normalized_key(key)
    for marker in _SENSITIVE_KEY_MARKERS:
        if marker in normalized:
            return f"sensitive_key_{marker}"
    return None


def _raw_credential_category(value: str) -> str | None:
    stripped = value.strip()
    if "-----BEGIN " in stripped.upper() and "PRIVATE KEY-----" in stripped.upper():
        return "private_key_material"
    if _JWT.search(stripped):
        return "jwt_material"
    if _KNOWN_SECRET_PREFIX.match(stripped):
        return "known_credential_prefix"
    if _AUTHORIZATION_CREDENTIAL.search(stripped):
        return "authorization_credential"
    if _CLOUD_CONNECTION_CREDENTIAL.search(stripped):
        return "cloud_connection_credential"
    # Prefix detection is useful for well-known providers, but it is not a
    # complete secret policy.  Reject opaque, high-entropy bearer-shaped
    # strings even when a provider uses an undocumented or newly introduced
    # prefix.  UUIDs and ordinary slugs intentionally fail this conservative
    # shape test (they do not contain three distinct character classes).
    if _OPAQUE_TOKEN_SHAPE.fullmatch(stripped):
        classes = sum(
            (
                bool(re.search(r"[a-z]", stripped)),
                bool(re.search(r"[A-Z]", stripped)),
                bool(re.search(r"[0-9]", stripped)),
                bool(re.search(r"[_-]", stripped)),
            )
        )
        if classes >= 3:
            frequencies = {character: stripped.count(character) for character in set(stripped)}
            entropy = -sum(
                (count / len(stripped)) * math.log2(count / len(stripped))
                for count in frequencies.values()
            )
            if entropy >= 4.25:
                return "opaque_high_entropy_credential"
    if _LABELED_CREDENTIAL.search(stripped):
        return "labeled_credential_material"
    if "://" in stripped:
        parsed = urlparse(stripped)
        if parsed.username is not None or parsed.password is not None:
            return "credential_bearing_url"
    return None


def _decode_url_components(value: str) -> str:
    """Decode a bounded number of URL layers before security checks."""

    decoded = value
    for _ in range(3):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    return decoded


def inspect_platform_configuration_material(
    value: object,
    *,
    reason: str | None = None,
) -> ConfigurationInspection:
    if not isinstance(value, dict):
        raise PlatformConfigurationValidationError("configuration value must be a JSON object")
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PlatformConfigurationValidationError(
            "configuration value must contain only finite JSON values"
        ) from exc
    if len(encoded) > MAX_CONFIGURATION_BYTES:
        raise PlatformConfigurationValidationError(
            f"configuration value exceeds {MAX_CONFIGURATION_BYTES} bytes"
        )

    findings: set[str] = set()
    nodes = 0

    def walk(item: object, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_CONFIGURATION_NODES:
            raise PlatformConfigurationValidationError(
                f"configuration value exceeds {MAX_CONFIGURATION_NODES} nodes"
            )
        if depth > MAX_CONFIGURATION_DEPTH:
            raise PlatformConfigurationValidationError(
                f"configuration value exceeds depth {MAX_CONFIGURATION_DEPTH}"
            )
        if isinstance(item, dict):
            for key, nested in item.items():
                if not isinstance(key, str):
                    raise PlatformConfigurationValidationError(
                        "configuration object keys must be strings"
                    )
                if not key or len(key) > MAX_CONFIGURATION_KEY_LENGTH:
                    raise PlatformConfigurationValidationError(
                        "configuration object key length is invalid"
                    )
                category = _sensitive_key_category(key)
                if category is not None:
                    findings.add(category)
                walk(nested, depth + 1)
        elif isinstance(item, list):
            for nested in item:
                walk(nested, depth + 1)
        elif isinstance(item, str):
            category = _raw_credential_category(item)
            if category is not None:
                findings.add(category)

    walk(value, 0)
    if reason:
        category = _raw_credential_category(reason)
        if category is not None:
            findings.add(f"reason_{category}")
    return ConfigurationInspection(
        serialized_size=len(encoded),
        finding_categories=tuple(sorted(findings)),
    )


def validate_secret_manager_reference(reference: str) -> str:
    canonical = reference.strip()
    if len(canonical) > 512 or any(ord(character) < 32 for character in canonical):
        raise PlatformConfigurationValidationError("secret reference is malformed")
    parsed = urlparse(canonical)
    decoded_path = _decode_url_components(parsed.path)
    decoded_reference = _decode_url_components(canonical)
    decoded_parsed = urlparse(decoded_reference)
    path_segments = [segment for segment in decoded_path.split("/") if segment]
    if (
        parsed.scheme.casefold() not in _SECRET_REFERENCE_SCHEMES
        or not parsed.netloc
        or not path_segments
        or parsed.username is not None
        or parsed.password is not None
        or parsed.params
        or parsed.query
        or parsed.fragment
        or any(segment in {".", ".."} for segment in path_segments)
        or any(character.isspace() for character in canonical)
        # Decode before checking URL delimiters so percent-encoded userinfo,
        # query, fragment, and traversal attempts cannot enter persistence.
        or decoded_parsed.username is not None
        or decoded_parsed.password is not None
        or decoded_parsed.params
        or decoded_parsed.query
        or decoded_parsed.fragment
        or any(character.isspace() for character in decoded_reference)
        or any(character in decoded_reference for character in ("@", "?", "#", "\\"))
        or _raw_credential_category(canonical) is not None
        or _raw_credential_category(decoded_reference) is not None
    ):
        raise PlatformConfigurationValidationError(
            "secret reference must identify an external supported Secret Manager object"
        )
    return canonical


def validate_platform_configuration_value(
    configuration_key: str,
    value: object,
    *,
    secret_reference: str | None,
    reason: str | None = None,
) -> dict[str, Any]:
    inspection = inspect_platform_configuration_material(value, reason=reason)
    if inspection.finding_categories:
        raise PlatformConfigurationValidationError(
            "configuration contains forbidden sensitive material"
        )
    schema = _SCHEMA_BY_KEY.get(configuration_key)
    if schema is None:
        raise PlatformConfigurationValidationError("configuration key is not supported")
    if secret_reference is not None:
        validate_secret_manager_reference(secret_reference)
    if configuration_key in {"identity"} and secret_reference is None:
        raise PlatformConfigurationValidationError(
            "identity configuration requires an external Secret Manager reference"
        )
    if (
        configuration_key == "event_stream"
        and isinstance(value, dict)
        and value.get("transport") in {"kafka", "nats"}
        and secret_reference is None
    ):
        raise PlatformConfigurationValidationError(
            "external event streams require an external Secret Manager reference"
        )
    try:
        parsed = schema.model_validate(value)
    except ValueError as exc:
        raise PlatformConfigurationValidationError(
            f"{configuration_key} does not match schema version 1"
        ) from exc
    canonical = parsed.model_dump(mode="json")
    canonical_inspection = inspect_platform_configuration_material(canonical)
    if canonical_inspection.finding_categories:
        raise PlatformConfigurationValidationError(
            "validated configuration contains forbidden sensitive material"
        )
    return canonical


def platform_configuration_schema_names() -> dict[str, str]:
    return {key: schema.__name__ for key, schema in _SCHEMA_BY_KEY.items()}
