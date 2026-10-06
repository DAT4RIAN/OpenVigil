import pytest

from windops_backend.errors import KnowledgeGraphUnavailableError, NotFoundError
from windops_backend.knowledge_graph.api import _available


async def test_failed_graph_read_is_actionable_without_logging_private_exception_values(caplog):
    sensitive_marker = "private-credential-and-source-content"

    async def failed_operation():
        raise TypeError(sensitive_marker)

    with pytest.raises(KnowledgeGraphUnavailableError) as raised:
        await _available(failed_operation())
    assert isinstance(raised.value.__cause__, TypeError)
    assert "TypeError" in caplog.text and "failed_operation" in caplog.text
    assert sensitive_marker not in caplog.text
    assert sensitive_marker not in str(raised.value)


async def test_expected_scope_denial_remains_domain_error_without_infrastructure_warning(caplog):
    async def denied_operation():
        raise NotFoundError("scope denied")

    with pytest.raises(NotFoundError):
        await _available(denied_operation())
    assert "Knowledge graph read failed" not in caplog.text
