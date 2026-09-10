from windops_backend.benchmarks.care import (
    anomaly,
    anomaly_runtime,
    fullscale,
    fullscale_evaluation,
    fullscale_import,
    pipeline,
    pipeline_runtime,
    scoring,
    scoring_prediction,
)
from windops_backend.benchmarks.care.evaluation import verify_evaluation_suite_artifact
from windops_backend.benchmarks.care.evaluation_artifact import (
    verify_evaluation_suite_artifact as owned_evaluation_verifier,
)


def test_legacy_care_modules_reexport_the_owned_contract_objects() -> None:
    assert anomaly.AnomalyFeatureWindow is anomaly_runtime.AnomalyFeatureWindow
    assert anomaly.build_governed_anomaly_output is anomaly_runtime.build_governed_anomaly_output
    assert pipeline.CareObjectStorageLayout is pipeline_runtime.CareObjectStorageLayout
    assert pipeline.FileBenchmarkJobControl is pipeline_runtime.FileBenchmarkJobControl
    assert scoring.ThresholdPolicy is scoring_prediction.ThresholdPolicy
    assert scoring.build_prediction_artifact is scoring_prediction.build_prediction_artifact
    assert fullscale.build_full_scale_import is fullscale_import.build_full_scale_import
    assert (
        fullscale.verify_full_scale_import_manifest
        is fullscale_import.verify_full_scale_import_manifest
    )
    assert fullscale.build_full_scale_evaluation is fullscale_evaluation.build_full_scale_evaluation
    assert (
        fullscale.verify_full_scale_evaluation_manifest
        is fullscale_evaluation.verify_full_scale_evaluation_manifest
    )
    assert verify_evaluation_suite_artifact is owned_evaluation_verifier
