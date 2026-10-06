import pytest

from windops_backend.structural_result_identity import structural_result_hash


def test_jsonb_equivalent_number_encodings_have_same_result_identity():
    before = {"zero": -0.0, "whole": 1e20, "fraction": 2.5e-19, "mode": [1.0, -0.0]}
    after = {
        "mode": [1, 0.0],
        "fraction": 0.00000000000000000025,
        "whole": 100000000000000000000,
        "zero": 0,
    }
    assert structural_result_hash(before) == structural_result_hash(after)


@pytest.mark.parametrize(
    "changed",
    [
        {"mode": [1.0000000000000002, 0]},
        {"mode": ["1", 0]},
        {"mode": [True, 0]},
        {"mode": {"0": 1, "1": 0}},
    ],
)
def test_result_identity_retains_precision_and_json_type(changed):
    assert structural_result_hash(changed) != structural_result_hash({"mode": [1.0, -0.0]})


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_results_cannot_receive_an_identity(number):
    with pytest.raises(ValueError, match="finite"):
        structural_result_hash({"mode": number})
