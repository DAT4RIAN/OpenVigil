"""JSONB representation changes preserve receipt identity; text/geometry changes do not."""

import pytest

from windops_backend.document_parse_result_identity import document_parse_result_hash


def test_jsonb_numbers_and_key_order_preserve_result_identity():
    original = {"body": "OCR +123.45 kN", "locator": {"bbox": [0.0, 2.5, 100.0, 30.0]}}
    persisted = {"locator": {"bbox": [0, 2.5, 100, 30]}, "body": "OCR +123.45 kN"}
    assert document_parse_result_hash(original) == document_parse_result_hash(persisted)
    for changed in (
        {**persisted, "body": "OCR -123.45 kN"},
        {**persisted, "locator": {"bbox": [0, 2.6, 100, 30]}},
        {**persisted, "locator": {"bbox": [False, 2.5, 100, 30]}},
    ):
        assert document_parse_result_hash(original) != document_parse_result_hash(changed)


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
def test_result_identity_rejects_non_finite_geometry(number):
    with pytest.raises(ValueError):
        document_parse_result_hash({"bbox": [0, number, 100, 30]})
