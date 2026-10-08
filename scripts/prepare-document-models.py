"""Prefetch public models in the dedicated parser environment, then freeze bytes.

Run from the repository root with the document parser Python, never the API Python.
This explicit preparation step needs network; conversion itself uses local models.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))

from windops_backend.document_parse_models import (
    MANIFEST_NAME,
    MAX_MODEL_BUNDLE_BYTES,
    verify_model_bundle,
)

MODEL_SNAPSHOTS = (
    (
        "docling-project/docling-layout-heron",
        "8f39ad3c0b4c58e9c2d2c84a38465abf757272d8",
        "apache-2.0",
        ["*.json", "*.safetensors", "README.md", "LICENSE*"],
    ),
    (
        "docling-project/docling-models",
        "fc0f2d45e2218ea24bce5045f58a389aed16dc23",
        "cdla-permissive-2.0",
        ["model_artifacts/tableformer/accurate/*", "README.md", "LICENSE*"],
    ),
)


def prepare(output: Path) -> str:
    from importlib.metadata import version

    import httpx
    from docling.models.stages.ocr.rapid_ocr_model import (
        RapidOcrModel,
        _backend_to_engine_type,
        _rapidocr_artifacts,
        _resolve_rapidocr,
    )
    from huggingface_hub import HfApi, snapshot_download
    from rapidocr.inference_engine.base import FileInfo, InferSession
    from rapidocr.utils.typings import ModelType, OCRVersion, TaskType

    if version("docling-slim") != "2.133.0" or version("rapidocr") != "3.9.2":
        raise ValueError(
            "prepare models using the fixed document parser dependency lock"
        )
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / MANIFEST_NAME
    if manifest_path.exists():
        digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        verify_model_bundle(output, digest)
        return digest
    sources = []
    api = HfApi(token=False)
    for repository, revision, license_id, patterns in MODEL_SNAPSHOTS:
        metadata = api.model_info(repository, revision=revision, token=False)
        if metadata.sha != revision or not metadata.card_data:
            raise ValueError("model source identity or license metadata is missing")
        if metadata.card_data.get("license") != license_id:
            raise ValueError("model source license differs from the selected snapshot")
        snapshot_download(
            repository,
            revision=revision,
            local_dir=output / repository.replace("/", "--"),
            allow_patterns=patterns,
            token=False,
            max_workers=2,
        )
        sources.append(
            {
                "name": repository,
                "source_url": f"https://huggingface.co/{repository}/tree/{revision}",
                "revision": revision,
                "license": license_id,
                "license_url": f"https://huggingface.co/{repository}/blob/{revision}/README.md",
            }
        )
    model_url = "https://modelscope.cn/api/v1/models/RapidAI/RapidOCR"
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        response = client.get(model_url)
        response.raise_for_status()
        if response.json()["Data"]["License"] != "Apache License 2.0":
            raise ValueError("RapidOCR model source license could not be verified")
        resolved = _resolve_rapidocr("ch", "onnxruntime")
        engine = _backend_to_engine_type("onnxruntime")
        model_dir = output / RapidOcrModel._model_repo_folder
        artifacts = _rapidocr_artifacts(
            model_dir,
            engine,
            resolved.ppocr_version,
            resolved.rapidocr_code,
            model_size="small",
        )
        infos = {
            "det": FileInfo(
                engine, resolved.ppocr_version, TaskType.DET, "ch", ModelType.SMALL
            ),
            "rec": FileInfo(
                engine, resolved.ppocr_version, TaskType.REC, "ch", ModelType.SMALL
            ),
            "cls": FileInfo(
                engine, OCRVersion.PPOCRV4, TaskType.CLS, "ch", ModelType.MOBILE
            ),
        }
        for task, artifact in artifacts.items():
            registry = InferSession.get_model_url(infos[task])
            for target, url in artifact.files.items():
                if registry["model_dir"] != url or "/resolve/v3.9.2/" not in url:
                    raise ValueError(
                        "OCR registry source differs from the fixed release"
                    )
                expected_sha = registry["SHA256"]
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    with target.open("rb") as stream:
                        observed = hashlib.file_digest(stream, "sha256").hexdigest()
                    if observed != expected_sha:
                        raise ValueError(
                            "existing OCR model does not match the registry hash"
                        )
                else:
                    temporary = target.with_suffix(".download-part")
                    digest = hashlib.sha256()
                    size = 0
                    with (
                        client.stream("GET", url) as download,
                        temporary.open("wb") as stream,
                    ):
                        download.raise_for_status()
                        for chunk in download.iter_bytes(1024 * 1024):
                            size += len(chunk)
                            if size > MAX_MODEL_BUNDLE_BYTES:
                                raise ValueError(
                                    "OCR model exceeds the preparation byte limit"
                                )
                            stream.write(chunk)
                            digest.update(chunk)
                    if digest.hexdigest() != expected_sha:
                        raise ValueError(
                            "downloaded OCR model does not match the registry hash"
                        )
                    temporary.replace(target)
                sources.append(
                    {
                        "name": f"RapidOCR/{task}",
                        "source_url": url,
                        "revision": f"v3.9.2;sha256={expected_sha}",
                        "license": "apache-2.0",
                        "license_url": model_url,
                    }
                )
    files = []
    for path in sorted(output.rglob("*")):
        if not path.is_file() or ".cache" in path.relative_to(output).parts:
            continue
        if path.name == MANIFEST_NAME:
            continue
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        files.append(
            {
                "path": path.relative_to(output).as_posix(),
                "sha256": digest,
                "size_bytes": path.stat().st_size,
            }
        )
    raw = (
        json.dumps(
            {
                "contract": "openvigil.document-models.v1",
                "docling_version": "2.133.0",
                "sources": sources,
                "files": files,
            },
            indent=2,
            sort_keys=True,
        ).encode()
        + b"\n"
    )
    manifest_path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    verify_model_bundle(output, digest)
    return digest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    print(prepare(arguments.output.resolve()))
