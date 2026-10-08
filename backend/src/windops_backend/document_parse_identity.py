"""Frozen parser identity shared without importing any OCR libraries."""

import hashlib
from importlib.metadata import version
from pathlib import Path

DOCUMENT_PARSER_VERSIONS = {
    "docling-slim": "2.133.0",
    "docling-core": "2.100.0",
    "docling-parse": "7.22.2",
    "docling-ibm-models": "4.0.3",
    "rapidocr": "3.9.2",
    "onnxruntime": "1.30.0",
    "numpy": "2.5.3",
    "scipy": "1.18.1",
    "torch": "2.14.1+cpu",
    "torchvision": "0.29.1+cpu",
    "pypdfium2": "5.14.0",
    "pypdf": "6.17.0",
}
EXECUTION_MODULES = (
    "document_parse_compute.py",
    "document_parse_contract.py",
    "document_parse_identity.py",
    "document_parse_models.py",
    "document_parse_process.py",
    "document_parse_result_identity.py",
    "structural_result_identity.py",
)


def parser_code_identity() -> dict[str, str]:
    root = Path(__file__).resolve().parent
    identity = {}
    for name in EXECUTION_MODULES:
        # Normalize checkout line endings, keeping every source token unchanged.
        raw = (root / name).read_bytes().replace(b"\r\n", b"\n")
        identity[name] = hashlib.sha256(raw).hexdigest()
    return identity


def observed_parser_versions() -> dict[str, str]:
    observed = {name: version(name) for name in DOCUMENT_PARSER_VERSIONS}
    if observed != DOCUMENT_PARSER_VERSIONS:
        raise RuntimeError("document parser numerical packages differ from the frozen contract")
    return observed
