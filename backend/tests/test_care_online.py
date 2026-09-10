from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr

from test_care_evaluation import _build_evaluations, _canonical_hash, _load_artifact
from windops_backend.benchmarks.care.evaluation import (
    CareOfflineEvaluationError,
    score_offline_model_package,
    verify_offline_model_package,
)
from windops_backend.benchmarks.care.online import (
    CareJsonPackageInferenceClient,
    load_replay_rows,
    normalized_online_score,
    online_threshold_policy,
    replay_variables_from_import,
    select_online_window,
)
from windops_backend.benchmarks.care.scoring import CareScoreError
from windops_backend.config import ModelInferenceTarget


@pytest.mark.asyncio
async def test_truth_free_window_recomputes_the_immutable_package_scores(
    tmp_path: Path,
) -> None:
    _, _, imported, import_root, output_root, built = _build_evaluations(tmp_path)
    model = next(
        value
        for value in built.manifest["models"]
        if value["algorithm"] == "care-random-projection-ensemble-v1"
    )
    package = _load_artifact(output_root, model["package"])
    verify_offline_model_package(package)
    variables = replay_variables_from_import(
        imported.manifest,
        import_root,
        feature_columns=package["feature_columns"],
    )
    threshold = online_threshold_policy(package)
    client = CareJsonPackageInferenceClient(package)

    for reference in model["prediction_artifacts"]:
        prediction = _load_artifact(output_root, reference)
        selection = select_online_window(prediction)
        assert selection.prediction_truth_used is False
        rows = load_replay_rows(
            imported.manifest,
            import_root,
            event_id=selection.event_id,
            start_source_row_id=selection.start_source_row_id,
            end_source_row_id=selection.end_source_row_id,
            variables=variables,
        )
        expected_by_row = {
            int(point["source_row_id"]): point
            for point in prediction["points"]
            if selection.start_source_row_id
            <= int(point["source_row_id"])
            <= selection.end_source_row_id
        }
        for row in rows:
            feature_values = dict(row.values)
            raw_score = score_offline_model_package(
                package,
                event_id=selection.event_id,
                feature_values=feature_values,
            )
            expected = expected_by_row[row.source_row_id]
            assert raw_score == pytest.approx(float(expected["anomaly_score"]), abs=1e-12)
            online_score = normalized_online_score(
                raw_score,
                float(package["threshold_policy"]["value"]),
            )
            assert (online_score > threshold.value) is bool(expected["binary_prediction"])
            output, _latency = await client.predict(
                ModelInferenceTarget(
                    endpoint_url="https://care-model.invalid/v1/predict",
                    api_token=SecretStr("not-used-by-safe-json-adapter"),
                ),
                {
                    "model": {"id": package["model_id"], "version": package["model_version"]},
                    "inputs": {
                        "event_id": selection.event_id,
                        "signals": [
                            {
                                "source_sequence": row.source_row_id,
                                "variable": variable,
                                "value": value,
                            }
                            for variable, value in row.values
                        ],
                    },
                },
                idempotency_key=f"windops:anomaly:test:{row.source_row_id}",
            )
            assert output["anomaly_score"] == pytest.approx(online_score, abs=1e-15)
            assert output["binary_prediction"] is bool(expected["binary_prediction"])
            assert "ground_truth" not in json.dumps(output)

    tampered_package = copy.deepcopy(package)
    tampered_package["event_profiles"][0]["means"][0] += 1
    with pytest.raises(CareOfflineEvaluationError, match="identity is invalid"):
        verify_offline_model_package(tampered_package)

    prediction = _load_artifact(output_root, model["prediction_artifacts"][0])
    leaked = copy.deepcopy(prediction)
    leaked["points"][0]["ground_truth"] = True
    unsigned: dict[str, Any] = {
        key: value for key, value in leaked.items() if key != "prediction_artifact_sha256"
    }
    leaked["prediction_artifact_sha256"] = _canonical_hash(unsigned)
    with pytest.raises(CareScoreError, match="forbidden truth"):
        select_online_window(leaked)
