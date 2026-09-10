import hashlib
from types import SimpleNamespace
from typing import Any, cast

import pytest
from minio import Minio

from windops_backend.storage import MinioArtifactVerifier


class ObjectResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def stream(self, amt: int) -> list[bytes]:
        return [self.body[index : index + amt] for index in range(0, len(self.body), amt)]

    def close(self) -> None:
        pass

    def release_conn(self) -> None:
        pass


class FakeMinio:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def bucket_exists(self, bucket: str) -> bool:
        return bucket == "windops-field-evidence"

    def presigned_put_object(self, bucket: str, object_name: str, **kwargs: Any) -> str:
        del kwargs
        return f"https://objects.example/{bucket}/{object_name}?signed=true"

    def stat_object(self, bucket: str, object_name: str) -> Any:
        assert bucket == "windops-field-evidence"
        assert object_name.startswith("work-orders/")
        return SimpleNamespace(size=len(self.body), content_type="application/json")

    def get_object(self, bucket: str, object_name: str) -> ObjectResponse:
        assert bucket == "windops-field-evidence"
        assert object_name.startswith("work-orders/")
        return ObjectResponse(self.body)


async def test_minio_upload_is_task_scoped_and_content_verified() -> None:
    body = b'{"measurement": 42}'
    verifier = MinioArtifactVerifier(cast(Minio, FakeMinio(body)), "windops-field-evidence")
    digest = hashlib.sha256(body).hexdigest()
    upload = await verifier.create_upload(
        bucket="windops-field-evidence",
        work_order_id="WO-42",
        task_id="TASK-7",
        file_name="../field evidence.json",
        content_type="application/json",
        artifact_sha256=digest,
    )
    assert upload["artifact_uri"].startswith(
        "minio://windops-field-evidence/work-orders/WO-42/tasks/TASK-7/"
    )
    assert upload["required_headers"] == {"content-type": "application/json"}
    await verifier.verify(
        upload["artifact_uri"],
        digest,
        work_order_id="WO-42",
        task_id="TASK-7",
    )

    with pytest.raises(ValueError, match="does not belong"):
        await verifier.verify(
            upload["artifact_uri"],
            digest,
            work_order_id="WO-42",
            task_id="TASK-8",
        )
    with pytest.raises(ValueError, match="SHA-256"):
        await verifier.verify(
            upload["artifact_uri"],
            "0" * 64,
            work_order_id="WO-42",
            task_id="TASK-7",
        )
