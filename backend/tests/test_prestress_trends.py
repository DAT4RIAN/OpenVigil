from windops_backend.services.structural import prestress_page_trends


def reading(identity, value, time, calibration="r1", source="synthetic_test"):
    return {
        "id": identity,
        "value_kn": value,
        "observed_at": time,
        "calibration_version": calibration,
        "source_kind": source,
        "sensor_id": "F1",
        "tendon_id": "T1",
        "artifact_sha256": "a" * 64,
        "uncertainty": {"status": "unquantified"},
    }


def test_direct_trend_preserves_measurements_without_inferred_loss_or_uncertainty():
    rows = [
        reading("second", 119, "2026-10-02T00:00:00Z"),
        reading("first", 123, "2026-10-01T00:00:00Z"),
    ]
    trend = prestress_page_trends(rows)[0]
    assert trend["change_kn"] == -4
    assert trend["status"] == "raw_change_available"
    assert trend["loss_percentage"] is None
    assert trend["uncertainty_status"] == "not_combined"
    assert trend["environmental_compensation"] == "unavailable"
    assert trend["scope"] == "returned_page_only"
    assert [p["observation_id"] for p in trend["points"]] == ["first", "second"]


def test_different_calibration_or_source_never_forms_one_trend():
    rows = [
        reading("first", 123, "2026-10-01T00:00:00Z"),
        reading("new-cal", 119, "2026-10-02T00:00:00Z", calibration="r2"),
        reading("field", 119, "2026-10-02T00:00:00Z", source="field_measurement"),
    ]
    trends = prestress_page_trends(rows)
    assert len(trends) == 3
    assert all(t["status"] == "insufficient_windows" and t["change_kn"] is None for t in trends)


def test_simultaneous_measurements_do_not_imply_temporal_change():
    rows = [reading("a", 123, "2026-10-01T00:00:00Z"), reading("b", 119, "2026-10-01T00:00:00Z")]
    assert prestress_page_trends(rows)[0]["change_kn"] is None
