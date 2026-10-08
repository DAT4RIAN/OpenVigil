"""Verify a pre-fetched, operator-pinned model bundle before opening a PDF."""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field

MANIFEST_NAME = "openvigil-model-manifest.json"
MAX_MODEL_BUNDLE_BYTES = 2 * 1024 * 1024 * 1024


class ModelFile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    path: str = Field(min_length=1, max_length=512)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=1, le=MAX_MODEL_BUNDLE_BYTES)


class ModelSource(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    name: str = Field(min_length=1, max_length=160)
    source_url: str = Field(pattern=r"^https://", max_length=1024)
    revision: str = Field(min_length=1, max_length=160)
    license: str = Field(min_length=1, max_length=160)
    license_url: str = Field(pattern=r"^https://", max_length=1024)


class ModelManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    contract: str = Field(pattern=r"^openvigil\.document-models\.v1$")
    docling_version: str = Field(pattern=r"^2\.133\.0$")
    sources: list[ModelSource] = Field(min_length=3, max_length=16)
    files: list[ModelFile] = Field(min_length=3, max_length=256)


def verify_model_bundle(directory: Path, expected_sha256: str) -> ModelManifest:
    directory = directory.resolve(strict=True)
    manifest_path = directory / MANIFEST_NAME
    if manifest_path.is_symlink() or manifest_path.stat().st_size > 256 * 1024:
        raise ValueError("document model manifest exceeds its limit or is linked")
    raw = manifest_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("document model manifest identity does not match trusted configuration")
    manifest = ModelManifest.model_validate_json(raw)
    paths: set[str] = set()
    total = 0
    for entry in manifest.files:
        relative = PurePosixPath(entry.path)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or "\\" in entry.path
            or ":" in entry.path
            or entry.path == MANIFEST_NAME
            or entry.path in paths
        ):
            raise ValueError("document model manifest contains an unsafe or duplicate path")
        target = directory.joinpath(*relative.parts)
        if target.is_symlink() or any(parent.is_symlink() for parent in target.parents):
            raise ValueError("document model file is linked")
        if not target.resolve(strict=True).is_relative_to(directory):
            raise ValueError("document model file is outside its bundle")
        if target.stat().st_size != entry.size_bytes:
            raise ValueError("document model file size does not match its identity")
        total += entry.size_bytes
        if total > MAX_MODEL_BUNDLE_BYTES:
            raise ValueError("document model bundle exceeds its byte limit")
        with target.open("rb") as stream:
            observed = hashlib.file_digest(stream, "sha256").hexdigest()
        if observed != entry.sha256:
            raise ValueError("document model file hash does not match its identity")
        paths.add(entry.path)
    actual = {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file() and ".cache" not in path.relative_to(directory).parts
    } - {MANIFEST_NAME}
    if actual != paths:
        raise ValueError("document model bundle contains unrecorded or missing files")
    return manifest
