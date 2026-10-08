"""Knowledge artifact limits shared by indexing and engineering evidence readers."""

KNOWLEDGE_DOCUMENT_INDEX_REQUESTED = "knowledge.document.index.requested"
KNOWLEDGE_DOCUMENT_PARSE_REQUESTED = "knowledge.document.parse.requested"
MAX_KNOWLEDGE_ARTIFACT_BYTES = 50 * 1024 * 1024
MAX_EXTRACTED_TEXT_CHARACTERS = 4_000_000
ALLOWED_KNOWLEDGE_CONTENT_TYPES = frozenset(
    {
        "text/plain",
        "text/markdown",
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)
