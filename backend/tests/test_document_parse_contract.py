import copy
import hashlib
import json

import pytest

from windops_backend.document_parse_contract import DocumentParseResult
from windops_backend.document_parse_models import MANIFEST_NAME, verify_model_bundle


def document_result():
    text = "混塔复测 +123.45 kN"
    return {
        "contract": "openvigil.document-parse.v1",
        "source_sha256": "a" * 64,
        "model_manifest_sha256": "b" * 64,
        "execution_code_sha256": {},
        "library_versions": {},
        "body": text,
        "source_page_count": 2,
        "passages": [
            {
                "ordinal": 0,
                "text": text,
                "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "char_start": 0,
                "char_end": len(text),
                "parser_version": "openvigil.document-parse.v1;unit-contract",
                "page_number": 2,
                "native_locator": {
                    "kind": "docling_pdf_item",
                    "requires_numeric_review": True,
                    "regions": [
                        {
                            "page_number": 2,
                            "bbox": [10.0, 10.0, 100.0, 40.0],
                            "page_width": 200.0,
                            "page_height": 300.0,
                            "coordinate_space": "pdf_points_top_left",
                        }
                    ],
                },
            }
        ],
    }


def test_contract_preserves_blank_page_number_numeric_text_and_hash():
    result = DocumentParseResult.model_validate(document_result())
    assert result.source_page_count == 2
    assert result.passages[0].page_number == 2
    assert result.passages[0].text == "混塔复测 +123.45 kN"


@pytest.mark.parametrize(
    "mutation",
    ["wrong_hash", "wrong_span", "omitted_text", "wrong_page", "negative", "nan", "boolean"],
)
def test_contract_rejects_unverifiable_text_or_page_geometry(mutation):
    payload = document_result()
    piece = payload["passages"][0]
    region = piece["native_locator"]["regions"][0]
    if mutation == "wrong_hash":
        piece["text_sha256"] = "c" * 64
    elif mutation == "wrong_span":
        piece["char_end"] -= 1
    elif mutation == "omitted_text":
        payload["body"] += " unseen"
    elif mutation == "wrong_page":
        region["page_number"] = 1
    elif mutation == "negative":
        region["bbox"][0] = -1.0
    elif mutation == "nan":
        region["bbox"][0] = float("nan")
    elif mutation == "boolean":
        region["page_width"] = True
    with pytest.raises(ValueError):
        DocumentParseResult.model_validate(payload)


def model_bundle(directory):
    files = []
    for index in range(3):
        content = f"arbitrary model identity bytes {index}".encode()
        path = f"model-{index}.bin"
        (directory / path).write_bytes(content)
        files.append(
            {
                "path": path,
                "sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
        )
    manifest = {
        "contract": "openvigil.document-models.v1",
        "docling_version": "2.133.0",
        "sources": [
            {
                "name": f"identity-test-{index}",
                "source_url": "https://example.invalid/identity-test",
                "revision": "identity-test",
                "license": "test-only",
                "license_url": "https://example.invalid/identity-test",
            }
            for index in range(3)
        ],
        "files": files,
    }
    raw = json.dumps(manifest).encode()
    (directory / MANIFEST_NAME).write_bytes(raw)
    return manifest, hashlib.sha256(raw).hexdigest()


def test_model_identity_checks_real_bytes_and_rejects_changed_or_unrecorded_files(tmp_path):
    _manifest, digest = model_bundle(tmp_path)
    assert len(verify_model_bundle(tmp_path, digest).files) == 3
    original = (tmp_path / "model-0.bin").read_bytes()
    (tmp_path / "model-0.bin").write_bytes(b"x" * len(original))
    with pytest.raises(ValueError, match="hash"):
        verify_model_bundle(tmp_path, digest)
    (tmp_path / "model-0.bin").write_bytes(original)
    (tmp_path / "unrecorded-model.bin").write_bytes(b"unrecorded")
    with pytest.raises(ValueError, match="unrecorded"):
        verify_model_bundle(tmp_path, digest)


@pytest.mark.parametrize("path", ["../outside.bin", "C:/outside.bin", "model-0.bin"])
def test_pinned_manifest_still_rejects_traversal_and_duplicate_paths(tmp_path, path):
    manifest, _digest = model_bundle(tmp_path)
    changed = copy.deepcopy(manifest)
    changed["files"][1]["path"] = path
    raw = json.dumps(changed).encode()
    (tmp_path / MANIFEST_NAME).write_bytes(raw)
    with pytest.raises(ValueError, match="unsafe or duplicate"):
        verify_model_bundle(tmp_path, hashlib.sha256(raw).hexdigest())


def test_model_manifest_itself_must_match_trusted_pin(tmp_path):
    model_bundle(tmp_path)
    with pytest.raises(ValueError, match="trusted configuration"):
        verify_model_bundle(tmp_path, "a" * 64)
