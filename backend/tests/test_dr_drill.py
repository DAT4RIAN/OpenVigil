import pytest

from windops_backend.config import Settings
from windops_backend.enums import Environment
from windops_backend.operations.dr_drill import validate_drill_targets


def _settings(database: str, bucket_suffix: str) -> Settings:
    return Settings(
        environment=Environment.TEST,
        database_url=f"postgresql+asyncpg://windops:secret@db/{database}",
        knowledge_graph_backend="memory",
        minio_field_evidence_bucket=f"field-{bucket_suffix}",
        minio_knowledge_bucket=f"knowledge-{bucket_suffix}",
        minio_model_bucket=f"model-{bucket_suffix}",
        minio_twin_bucket=f"twin-{bucket_suffix}",
        minio_care_bucket=f"care-{bucket_suffix}",
    )


def test_drill_requires_isolated_database_and_buckets() -> None:
    source = _settings("windops", "source")
    target = _settings("windops_drill", "target")
    assert validate_drill_targets(source, target) == "windops_drill"

    with pytest.raises(ValueError, match="database must be isolated"):
        validate_drill_targets(source, _settings("windops", "target"))
    overlapping = _settings("windops_drill", "target").model_copy(
        update={"minio_model_bucket": source.minio_model_bucket}
    )
    with pytest.raises(ValueError, match="buckets must be isolated"):
        validate_drill_targets(source, overlapping)
    care_overlap = _settings("windops_drill", "target").model_copy(
        update={"minio_care_bucket": source.minio_care_bucket}
    )
    with pytest.raises(ValueError, match="windops-care|care-source"):
        validate_drill_targets(source, care_overlap)
