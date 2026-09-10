from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import create_async_engine

import windops_backend.benchmarks.care.fullscale_evaluation as _fullscale_evaluation
import windops_backend.benchmarks.care.fullscale_import as _fullscale_import
from windops_backend.benchmarks.care.pipeline import (
    FileBenchmarkJobControl,
    ImmutableArtifactStore,
    LocalImmutableArtifactStore,
    MinioImmutableArtifactStore,
)
from windops_backend.benchmarks.care.runtime import (
    care_minio_client,
    get_care_worker_settings,
)
from windops_backend.config import get_settings
from windops_backend.db import create_engine, create_session_factory
from windops_backend.operations.backups import minio_client

FULL_SCALE_IMPORT_VERSION = _fullscale_import.FULL_SCALE_IMPORT_VERSION
FULL_SCALE_IMPORT_SCHEMA_VERSION = _fullscale_import.FULL_SCALE_IMPORT_SCHEMA_VERSION
FULL_SCALE_EVENT_SCHEMA_VERSION = _fullscale_import.FULL_SCALE_EVENT_SCHEMA_VERSION
FULL_SCALE_EVALUATION_VERSION = _fullscale_import.FULL_SCALE_EVALUATION_VERSION
FULL_SCALE_EVALUATION_SCHEMA_VERSION = _fullscale_import.FULL_SCALE_EVALUATION_SCHEMA_VERSION
FULL_SCALE_FOLD_SCHEMA_VERSION = _fullscale_import.FULL_SCALE_FOLD_SCHEMA_VERSION
FULL_SCALE_MODEL_SCHEMA_VERSION = _fullscale_import.FULL_SCALE_MODEL_SCHEMA_VERSION
FULL_SCALE_PREDICTION_FREEZE_SCHEMA_VERSION = (
    _fullscale_import.FULL_SCALE_PREDICTION_FREEZE_SCHEMA_VERSION
)
FULL_SCALE_RESOURCE_POLICY_VERSION = _fullscale_import.FULL_SCALE_RESOURCE_POLICY_VERSION
FULL_SCALE_OPERATIONAL_POLICY_VERSION = _fullscale_import.FULL_SCALE_OPERATIONAL_POLICY_VERSION
FULL_SCALE_PROTOCOL_FROZEN_AT = _fullscale_import.FULL_SCALE_PROTOCOL_FROZEN_AT
FULL_SCALE_THRESHOLD = _fullscale_import.FULL_SCALE_THRESHOLD
FULL_SCALE_THRESHOLD_VERSION = _fullscale_import.FULL_SCALE_THRESHOLD_VERSION
FULL_SCALE_THRESHOLD_RUN_ID = _fullscale_import.FULL_SCALE_THRESHOLD_RUN_ID
FULL_SCALE_MODEL_VERSION = _fullscale_import.FULL_SCALE_MODEL_VERSION
FULL_SCALE_QUALITY_MASK_POLICY_VERSION = _fullscale_import.FULL_SCALE_QUALITY_MASK_POLICY_VERSION
FULL_SCALE_TRAIN_STATUS_IDS = _fullscale_import.FULL_SCALE_TRAIN_STATUS_IDS
FULL_SCALE_STAGE_ORDER = _fullscale_import.FULL_SCALE_STAGE_ORDER
MIN_REPLAY_WRITE_ROWS_PER_SECOND = _fullscale_import.MIN_REPLAY_WRITE_ROWS_PER_SECOND
CareFullScaleError = _fullscale_import.CareFullScaleError
CareFullScaleResourceError = _fullscale_import.CareFullScaleResourceError
FullScaleExpectedCounts = _fullscale_import.FullScaleExpectedCounts
CARE_V6_FULL_SCALE_COUNTS = _fullscale_import.CARE_V6_FULL_SCALE_COUNTS
FullScaleResourceLimits = _fullscale_import.FullScaleResourceLimits
DEFAULT_FULL_SCALE_RESOURCE_LIMITS = _fullscale_import.DEFAULT_FULL_SCALE_RESOURCE_LIMITS
_FarmContract = _fullscale_import._FarmContract
_FullScaleContract = _fullscale_import._FullScaleContract
FullScaleImportResult = _fullscale_import.FullScaleImportResult
FullScaleEvaluationResult = _fullscale_import.FullScaleEvaluationResult
FullScaleImportRegistration = _fullscale_import.FullScaleImportRegistration
FullScaleEvaluationRegistration = _fullscale_import.FullScaleEvaluationRegistration
_canonical_bytes = _fullscale_import._canonical_bytes
_canonical_hash = _fullscale_import._canonical_hash
_resolved_artifact_root = _fullscale_import._resolved_artifact_root
_is_sha256 = _fullscale_import._is_sha256
_safe_token = _fullscale_import._safe_token
_license = _fullscale_import._license
_verify_license = _fullscale_import._verify_license
_build_contract = _fullscale_import._build_contract
build_full_scale_plan = _fullscale_import.build_full_scale_plan
_event_summary_path = _fullscale_import._event_summary_path
_verify_event_summary = _fullscale_import._verify_event_summary
_load_existing_event_summary = _fullscale_import._load_existing_event_summary
_resource_max = _fullscale_import._resource_max
_audit_with_process_resources = _fullscale_import._audit_with_process_resources
_enforce_import_resources = _fullscale_import._enforce_import_resources
build_full_scale_import = _fullscale_import.build_full_scale_import
verify_full_scale_import_manifest = _fullscale_import.verify_full_scale_import_manifest
register_full_scale_import = _fullscale_import.register_full_scale_import


_Moments = _fullscale_evaluation._Moments
_new_moments = _fullscale_evaluation._new_moments
_normalise_status = _fullscale_evaluation._normalise_status
_timestamp_text = _fullscale_evaluation._timestamp_text
_resolve_reference = _fullscale_evaluation._resolve_reference
_publish_self_hashed_json = _fullscale_evaluation._publish_self_hashed_json
_load_json_reference = _fullscale_evaluation._load_json_reference
_quality_mask_policy = _fullscale_evaluation._quality_mask_policy
_quality_mask_impact_summary = _fullscale_evaluation._quality_mask_impact_summary
_quality_mask_lineage = _fullscale_evaluation._quality_mask_lineage
_load_quality_mask_artifact = _fullscale_evaluation._load_quality_mask_artifact
_quality_mask_index = _fullscale_evaluation._quality_mask_index
_quality_mask_matrix = _fullscale_evaluation._quality_mask_matrix
_feature_matrix = _fullscale_evaluation._feature_matrix
_batch_values = _fullscale_evaluation._batch_values
_evaluation_column_contracts = _fullscale_evaluation._evaluation_column_contracts
_batch_status_evidence = _fullscale_evaluation._batch_status_evidence
_iter_event_batches = _fullscale_evaluation._iter_event_batches
_accumulate_moments = _fullscale_evaluation._accumulate_moments
_build_fold_profiles = _fullscale_evaluation._build_fold_profiles
_model_id = _fullscale_evaluation._model_id
_threshold_policy = _fullscale_evaluation._threshold_policy
_model_selection = _fullscale_evaluation._model_selection
_build_prediction = _fullscale_evaluation._build_prediction
_truth_from_event = _fullscale_evaluation._truth_from_event
verify_full_scale_prediction_status_evidence = (
    _fullscale_evaluation.verify_full_scale_prediction_status_evidence
)
verify_full_scale_prediction_model_inputs = (
    _fullscale_evaluation.verify_full_scale_prediction_model_inputs
)
_operational_policy = _fullscale_evaluation._operational_policy
_verify_operational_policy = _fullscale_evaluation._verify_operational_policy
_verify_model_package = _fullscale_evaluation._verify_model_package
_evaluate_resource_gate = _fullscale_evaluation._evaluate_resource_gate
build_full_scale_evaluation = _fullscale_evaluation.build_full_scale_evaluation
verify_full_scale_evaluation_manifest = _fullscale_evaluation.verify_full_scale_evaluation_manifest
register_full_scale_evaluation = _fullscale_evaluation.register_full_scale_evaluation
resource_prediction_count = _fullscale_evaluation.resource_prediction_count


def _read_json(path: Path) -> Mapping[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise CareFullScaleError(f"JSON root must be an object: {path}")
    return raw


async def _register_from_settings(args: argparse.Namespace) -> dict[str, Any]:
    if args.use_care_worker_runtime:
        care_settings = get_care_worker_settings()
        engine = create_async_engine(
            care_settings.database_url.get_secret_value(),
            pool_pre_ping=True,
        )
    else:
        settings = get_settings()
        engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    try:
        source_manifest = _read_json(args.source_manifest)
        quality_contract = _read_json(args.quality_contract)
        import_manifest = _read_json(args.import_manifest)
        evaluation_manifest = _read_json(args.evaluation_manifest)
        async with session_factory() as session, session.begin():
            imported = await register_full_scale_import(
                session,
                import_manifest,
                source_manifest,
                quality_contract,
                artifact_root=args.artifact_root,
                tenant_id=args.tenant_id,
                subject=args.subject,
            )
            evaluated = await register_full_scale_evaluation(
                session,
                evaluation_manifest,
                import_manifest,
                artifact_root=args.artifact_root,
                subject=args.subject,
            )
        return {
            "import_created_count": imported.created_count,
            "import_replayed_count": imported.replayed_count,
            "evaluation_created_count": evaluated.created_count,
            "evaluation_replayed_count": evaluated.replayed_count,
            "dataset_version_id": imported.dataset_version_id,
            "event_database_ids": list(imported.event_ids),
            "model_ids": list(evaluated.model_ids),
            "evaluation_run_ids": list(evaluated.evaluation_run_ids),
        }
    finally:
        await engine.dispose()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run bounded CARE v6 full-scale import/evaluation")
    subparsers = parser.add_subparsers(dest="command", required=True)
    import_parser = subparsers.add_parser("import", help="build A -> C -> B full artifacts")
    import_parser.add_argument("--manifest", type=Path, required=True)
    import_parser.add_argument("--quality-contract", type=Path, required=True)
    import_parser.add_argument("--dataset-root", type=Path, required=True)
    import_parser.add_argument("--output-root", type=Path, required=True)
    import_parser.add_argument("--archive", type=Path)
    import_store = import_parser.add_mutually_exclusive_group()
    import_store.add_argument("--object-store-root", type=Path)
    import_store.add_argument("--use-configured-minio", action="store_true")
    import_store.add_argument("--use-care-worker-runtime", action="store_true")
    import_parser.add_argument("--job-id", default="care-v6-full-import")
    import_parser.add_argument("--state-path", type=Path)
    evaluate_parser = subparsers.add_parser("evaluate", help="run within-farm LOAO evaluation")
    evaluate_parser.add_argument("--import-manifest", type=Path, required=True)
    evaluate_parser.add_argument("--output-root", type=Path, required=True)
    evaluation_store = evaluate_parser.add_mutually_exclusive_group()
    evaluation_store.add_argument("--object-store-root", type=Path)
    evaluation_store.add_argument("--use-configured-minio", action="store_true")
    evaluation_store.add_argument("--use-care-worker-runtime", action="store_true")
    evaluate_parser.add_argument("--job-id", default="care-v6-full-evaluation")
    evaluate_parser.add_argument("--state-path", type=Path)
    register_parser = subparsers.add_parser(
        "register", help="atomically register verified import and evaluation manifests"
    )
    register_parser.add_argument("--source-manifest", type=Path, required=True)
    register_parser.add_argument("--quality-contract", type=Path, required=True)
    register_parser.add_argument("--import-manifest", type=Path, required=True)
    register_parser.add_argument("--evaluation-manifest", type=Path, required=True)
    register_parser.add_argument("--artifact-root", type=Path, required=True)
    register_parser.add_argument("--tenant-id", default="tenant-east-china")
    register_parser.add_argument("--subject", default="care-full-scale-worker")
    register_parser.add_argument("--use-care-worker-runtime", action="store_true")
    status_parser = subparsers.add_parser("status", help="verify and print a job state")
    status_parser.add_argument("--state-path", type=Path, required=True)
    cancel_parser = subparsers.add_parser(
        "cancel", help="request cancellation at the next durable event boundary"
    )
    cancel_parser.add_argument("--state-path", type=Path, required=True)
    return parser


def _artifact_store_from_args(args: argparse.Namespace) -> ImmutableArtifactStore | None:
    if args.use_care_worker_runtime:
        care_settings = get_care_worker_settings()
        return MinioImmutableArtifactStore(
            care_minio_client(care_settings),
            care_settings.minio_bucket,
        )
    if args.use_configured_minio:
        settings = get_settings()
        return MinioImmutableArtifactStore(
            minio_client(settings),
            settings.minio_care_bucket,
        )
    return (
        LocalImmutableArtifactStore(args.object_store_root)
        if args.object_store_root is not None
        else None
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command in {"status", "cancel"}:
        control = FileBenchmarkJobControl(args.state_path)
        state = control.request_cancel() if args.command == "cancel" else control.read()
        print(json.dumps(state.to_document(), ensure_ascii=False, sort_keys=True))
        return 0
    if args.command == "register":
        print(
            json.dumps(
                asyncio.run(_register_from_settings(args)),
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    store = _artifact_store_from_args(args)
    result: FullScaleImportResult | FullScaleEvaluationResult
    if args.command == "import":
        result = build_full_scale_import(
            _read_json(args.manifest),
            _read_json(args.quality_contract),
            args.dataset_root,
            args.output_root,
            source_archive_path=args.archive,
            artifact_store=store,
            job_id=args.job_id,
            state_path=args.state_path,
        )
    else:
        result = build_full_scale_evaluation(
            _read_json(args.import_manifest),
            args.output_root,
            artifact_store=store,
            job_id=args.job_id,
            state_path=args.state_path,
        )
    print(
        json.dumps(
            {
                "manifest_path": str(result.manifest_path),
                "manifest_file_sha256": result.manifest_file_sha256,
                "replayed": result.replayed,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
