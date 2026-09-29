import importlib.util
from pathlib import Path

from cryptography import x509


def runner_module():
    path = Path(__file__).parents[1] / "scripts/run_business_e2e.py"
    spec = importlib.util.spec_from_file_location("business_e2e_runner", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ephemeral_dependencies_have_no_external_volumes_or_fixed_ports() -> None:
    definition = runner_module().compose_definition("ephemeral-test-password")
    assert set(definition["services"]) == {"postgres", "redis", "minio", "neo4j"}
    assert all(value is None for value in definition["volumes"].values())
    for service in definition["services"].values():
        assert "@sha256:" in service["image"]
        assert all(port.startswith("127.0.0.1::") for port in service["ports"])
        assert "container_name" not in service
        for mount in service["volumes"]:
            assert mount.split(":")[0] in definition["volumes"]
    assert definition["services"]["postgres"]["environment"]["POSTGRES_PASSWORD"] == (
        "ephemeral-test-password"
    )


def test_private_ca_is_only_valid_for_loopback(tmp_path: Path) -> None:
    cert_path, key_path = runner_module().certificate(tmp_path)
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert [str(value) for value in names.get_values_for_type(x509.IPAddress)] == ["127.0.0.1"]
    assert names.get_values_for_type(x509.DNSName) == []
    assert key_path.parent == tmp_path
