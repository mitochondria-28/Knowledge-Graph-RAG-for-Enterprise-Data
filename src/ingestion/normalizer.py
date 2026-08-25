import re
import unicodedata


def normalize_text(text: str) -> str:
    """
    Clean raw document text while preserving Markdown structure.

    What we do and WHY:
    - Unicode NFC: ensures 'é' is stored as one codepoint, not two.
      Without this, the same word can have different byte representations,
      which breaks string matching and hashing.
    - Normalize line endings: Windows uses \r\n, Unix uses \n. We standardize.
    - Remove control characters: null bytes and other invisible characters
      that can corrupt downstream processing.
    - Collapse excessive blank lines: more than 2 consecutive blank lines add
      no semantic value and inflate chunk sizes.
    - Strip trailing whitespace: prevents invisible differences between
      otherwise identical lines from producing different hashes.
    """
    # Composed unicode form (e.g., é as single codepoint, not e + combining accent)
    text = unicodedata.normalize("NFC", text)

    # Standardize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Remove null bytes and non-printable control characters
    # Keep: \t (tab), \n (newline)
    text = re.sub(r"[\x00-\x08\x0b-\x0c\x0e-\x1f\x7f]", "", text)

    # Collapse 3+ consecutive blank lines down to 2
    text = re.sub(r"\n{4,}", "\n\n\n", text)

    # Strip trailing whitespace from every line
    text = "\n".join(line.rstrip() for line in text.splitlines())

    return text.strip()
