import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path

from src.ingestion.normalizer import normalize_text

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".md", ".txt", ".pdf"})

# Maps corpus sub-directory names → semantic doc_type labels
_DIR_TO_TYPE: dict[str, str] = {
    "companies": "company",
    "projects": "project",
    "technologies": "technology",
    "people": "people",
}


@dataclass
class RawDocument:
    """A single source document after loading and normalization."""

    file_path: Path
    content: str          # normalized text
    doc_type: str         # e.g. "company", "project", "technology"
    title: str            # extracted from first H1 or derived from filename
    doc_hash: str         # SHA-256 of normalized content
    char_count: int
    metadata: dict = field(default_factory=dict)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _infer_doc_type(file_path: Path) -> str:
    """Infer the document category from its parent directory name."""
    return _DIR_TO_TYPE.get(file_path.parent.name, "general")


def _extract_title(content: str, file_path: Path) -> str:
    """Return the first H1 heading, or a title derived from the filename."""
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return file_path.stem.replace("_", " ").title()


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ── Public API ────────────────────────────────────────────────────────────────

def _read_pdf(file_path: Path) -> str:
    from pypdf import PdfReader
    reader = PdfReader(str(file_path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)


def load_document(file_path: Path) -> RawDocument:
    """Load, normalize, and fingerprint a single document."""
    if file_path.suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported extension '{file_path.suffix}'. "
            f"Supported: {SUPPORTED_EXTENSIONS}"
        )

    if file_path.suffix == ".pdf":
        raw_text = _read_pdf(file_path)
    else:
        raw_text = file_path.read_text(encoding="utf-8")
    content = normalize_text(raw_text)

    return RawDocument(
        file_path=file_path,
        content=content,
        doc_type=_infer_doc_type(file_path),
        title=_extract_title(content, file_path),
        doc_hash=_sha256(content),
        char_count=len(content),
    )


def discover_documents(corpus_dir: Path) -> list[Path]:
    """Recursively find all supported documents, sorted for deterministic ordering."""
    paths: list[Path] = []
    for ext in SUPPORTED_EXTENSIONS:
        paths.extend(corpus_dir.rglob(f"*{ext}"))
    return sorted(paths)


def load_corpus(corpus_dir: Path) -> list[RawDocument]:
    """Load every document in corpus_dir. Logs but does not raise on individual failures."""
    if not corpus_dir.exists():
        raise FileNotFoundError(f"Corpus directory not found: {corpus_dir}")

    paths = discover_documents(corpus_dir)
    if not paths:
        logger.warning("No documents found in %s", corpus_dir)
        return []

    documents: list[RawDocument] = []
    for path in paths:
        try:
            doc = load_document(path)
            documents.append(doc)
            logger.debug("Loaded '%s' (%d chars, hash=%s)", path.name, doc.char_count, doc.doc_hash[:8])
        except Exception as exc:
            logger.error("Failed to load %s: %s", path, exc)

    logger.info("Loaded %d/%d documents from %s", len(documents), len(paths), corpus_dir)
    return documents
