"""Owned local registry/build and offline non-root OCR probe; no deployment."""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_IMAGE = "registry@sha256:a3d8aaa63ed8681a604f1dea0aa03f100d5895b6a58ace528858a7b332415373"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-base", required=True)
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    for path in (args.models, args.fixture):
        if not path.resolve().is_relative_to(ROOT / ".artifacts") or not path.exists():
            parser.error("Probe inputs must exist in this checkout's .artifacts")
    run_id = f"{datetime.now(UTC):%Y%m%d%H%M%S}-{secrets.token_hex(3)}"
    folder = ROOT / ".artifacts/document-parser-20261007" / f"image-{run_id}"
    context = folder / "context"
    context.mkdir(parents=True)
    backend = ROOT / "backend"
    selected = [
        backend / name
        for name in (
            "Dockerfile.document-parser",
            "requirements.container.txt",
            "requirements.document-parser.txt",
            "pyproject.toml",
        )
    ] + [
        path
        for path in (backend / "src").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    ]
    hashes = {}
    for path in selected:
        if (
            path.is_symlink()
            or path.suffix in {".pem", ".key", ".pyc"}
            or path.name.startswith(".env")
        ):
            raise RuntimeError("Unexpected build input")
        name = path.relative_to(backend).as_posix()
        target = context / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    revision = (
        "worktree-sha256:" + hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    )
    name = f"openvigil-document-registry-{run_id}"
    volume = name + "-data"
    tag = "openvigil-document-local:" + run_id
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

    def output(command: list[str]) -> str:
        return subprocess.check_output(
            command, cwd=ROOT, text=True, creationflags=creationflags
        ).strip()

    def logged(command: list[str], log_name: str, timeout: int = 1800) -> None:
        with (folder / log_name).open("w", encoding="utf-8") as stream:
            subprocess.run(
                command,
                cwd=ROOT,
                stdout=stream,
                stderr=subprocess.STDOUT,
                check=True,
                timeout=timeout,
                creationflags=creationflags,
            )

    report: dict[str, Any] = {
        "schema": "openvigil.document-image-local.v1",
        "passed": False,
        "cleanup_passed": False,
        "boundary": (
            "Local unsigned worktree image/offline synthetic OCR; "
            "not production or field acceptance"
        ),
        "source_files": hashes,
        "revision": revision,
        "registry": name,
        "registry_port": port,
    }
    registry_created = volume_created = False
    try:
        # Promote the actual local base to a fresh loopback registry so BuildKit
        # can resolve an immutable manifest without treating a local tag as Docker Hub.
        base = json.loads(output(["docker", "image", "inspect", args.api_base]))[0]
        if base["Config"]["User"] != "10001:10001":
            raise RuntimeError("The API base must be the non-root project runtime")
        report["historical_api_base_id"] = base["Id"]
        output(
            ["docker", "volume", "create", "--label", "openvigil.document-image=" + run_id, volume]
        )
        volume_created = True
        output(
            [
                "docker",
                "create",
                "--name",
                name,
                "--label",
                "openvigil.document-image=" + run_id,
                "-p",
                f"127.0.0.1:{port}:5000",
                "-v",
                volume + ":/var/lib/registry",
                REGISTRY_IMAGE,
            ]
        )
        registry_created = True
        output(["docker", "start", name])
        for _ in range(30):
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/v2/", timeout=2) as response:
                    if response.status == 200:
                        break
            except OSError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("Owned registry did not start")
        repository = f"127.0.0.1:{port}/openvigil/document-base"
        output(["docker", "tag", base["Id"], repository + ":staging"])
        logged(["docker", "push", repository + ":staging"], "base-registry.log")
        promoted = json.loads(output(["docker", "image", "inspect", repository + ":staging"]))[0]
        refs = [ref for ref in promoted["RepoDigests"] if ref.startswith(repository + "@sha256:")]
        if len(refs) != 1:
            raise RuntimeError("Expected exactly one promoted immutable base manifest")
        report["exact_base_ref"] = refs[0]
        print(f"Document image evidence: {folder}", flush=True)
        logged(
            [
                "docker",
                "buildx",
                "build",
                "--load",
                "--provenance=false",
                "--platform",
                "linux/amd64",
                "--build-arg",
                "BACKEND_IMAGE=" + refs[0],
                "--build-arg",
                "WINDOPS_RELEASE_ID=document-local-" + run_id,
                "--build-arg",
                "WINDOPS_COMMIT_SHA=" + revision,
                "--label",
                "org.openvigil.local-only=true",
                "--file",
                str(context / "Dockerfile.document-parser"),
                "--tag",
                tag,
                str(context),
            ],
            "build.log",
        )
        image = json.loads(output(["docker", "image", "inspect", tag]))[0]
        report["image_id"] = image["Id"]
        assert image["Config"]["User"] == "10001:10001"
        assert image["Config"]["Cmd"] == [
            "dramatiq",
            "windops_backend.document_parse_tasks",
            "--queues",
            "document-parse",
            "--processes",
            "1",
            "--threads",
            "1",
        ]
        manifest_sha = hashlib.sha256(
            (args.models / "openvigil-model-manifest.json").read_bytes()
        ).hexdigest()
        probe = folder / "probe.py"
        probe.write_text(
            '''import asyncio,hashlib,json,os
from pathlib import Path
from windops_backend.document_parse_process import parse_document_subprocess
from windops_backend.document_parse_identity import parser_code_identity
content=Path("/fixture/source.pdf").read_bytes()
result=asyncio.run(parse_document_subprocess(content,models_path=Path("/models"),manifest_sha256="'''
            + manifest_sha
            + """",python_executable="/opt/document-parser/bin/python"))
assert os.getuid()==10001 and result.source_page_count==2
assert len(result.passages)==15 and all(piece.page_number==2 for piece in result.passages)
assert sum("table_cell" in piece.native_locator for piece in result.passages)==9
assert result.source_sha256==hashlib.sha256(content).hexdigest()
assert result.execution_code_sha256==parser_code_identity()
for text in ("混塔预应力复测记录","+123.45 kN","-0.25 mm","118.20"):
    assert text in result.body
print(json.dumps({"uid":os.getuid(),"source_sha256":result.source_sha256,"page_count":2,"passages":15,"table_cells":9,"execution_code_sha256":result.execution_code_sha256,"observed_versions":result.library_versions}))
""",
            encoding="utf-8",
        )
        locked = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--memory",
            "3g",
            "--cpus",
            "2",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=256m,uid=10001,gid=10001",
            "--mount",
            f"type=bind,source={args.models.resolve()},target=/models,readonly",
            "--mount",
            f"type=bind,source={args.fixture.resolve()},target=/fixture/source.pdf,readonly",
            "--mount",
            f"type=bind,source={probe.resolve()},target=/probe.py,readonly",
        ]
        logged(locked + [tag, "python", "/probe.py"], "probe.log", timeout=240)
        report["probe"] = json.loads((folder / "probe.log").read_text())
        logged(
            [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                tag,
                "/opt/document-parser/bin/python",
                "-m",
                "pip",
                "check",
            ],
            "pip-check.log",
            timeout=30,
        )
        expected = {
            path.relative_to(backend / "src/windops_backend").as_posix(): hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
            for path in (backend / "src/windops_backend").rglob("*.py")
        }
        inventory_code = (
            "import json,hashlib; from pathlib import Path; import windops_backend; "
            "root=Path(windops_backend.__file__).parent; "
            "print(json.dumps({p.relative_to(root).as_posix():"
            "hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*.py')}))"
        )
        installed = json.loads(
            output(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "--read-only",
                    tag,
                    "python",
                    "-c",
                    inventory_code,
                ]
            )
        )
        if installed != expected:
            raise RuntimeError("Installed sources differ from the current checkout")
        report["installed_sources_verified"] = len(expected)
        for relative, digest in hashes.items():
            if hashlib.sha256((backend / relative).read_bytes()).hexdigest() != digest:
                raise RuntimeError("Build source changed while validating")
        report["passed"] = True
    except Exception as exc:
        report["error"] = type(exc).__name__
        print(f"Document image failed: {type(exc).__name__}", flush=True)
    finally:
        cleanup_errors = []
        if registry_created:
            try:
                logged(["docker", "rm", "--force", name], "registry-cleanup.log", timeout=30)
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
        if volume_created:
            try:
                logged(["docker", "volume", "rm", volume], "volume-cleanup.log", timeout=30)
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
        report["cleanup_passed"] = not cleanup_errors
        report["cleanup_errors"] = cleanup_errors
        report["finished_at"] = datetime.now(UTC).isoformat()
        (folder / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    raise SystemExit(0 if report["passed"] and report["cleanup_passed"] else 1)


if __name__ == "__main__":
    main()
