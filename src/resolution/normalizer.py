"""
Name normalization for entity resolution.

We normalize entity names into a comparison form — NOT a display form.
The canonical name (what appears in the graph) is chosen separately by
select_canonical_name(). Normalization is only used to compute similarity.

WHY SEPARATE NORMALIZATION FROM CANONICAL SELECTION:

If we normalized "TechNova Corporation" to "technova" and used that as the
canonical name, our graph would lose important information. Instead:

  normalize("TechNova Corporation") → "technova"          (for comparison)
  normalize("TechNova Corp")        → "technova"          (for comparison)
  normalize("TechNova")             → "technova"          (for comparison)

All three compare equal → same cluster → canonical = "TechNova Corporation"
(the most frequently occurring full name).

WHAT WE STRIP (legal suffixes only, not descriptive words):

  RIGHT: "Stellar Systems Inc." → "stellar systems"  (strip "Inc.")
  WRONG: "Stellar Systems"      → "stellar"          (don't strip "Systems" — it's part of the name)

  RIGHT: "TechNova Corporation" → "technova"         (strip "Corporation")
  WRONG: "Apex Analytics"       → "apex"             (don't strip "Analytics")
"""

import re
import unicodedata

# Legal entity suffixes that carry no semantic meaning about the entity's identity.
# We strip these when normalizing for comparison, not for display.
_LEGAL_SUFFIXES: frozenset[str] = frozenset({
    # English
    "corporation", "corp", "incorporated", "inc", "limited", "ltd",
    "llc", "plc", "lp", "co", "company",
    # European
    "gmbh", "ag", "sa", "nv", "bv", "ab", "oy",
})

# Personal honorifics — strip when normalizing person names.
_HONORIFICS: frozenset[str] = frozenset({
    "dr", "mr", "mrs", "ms", "miss", "prof", "professor", "sir", "dame",
})


def normalize_for_comparison(name: str) -> str:
    """
    Produce a lowercase, punctuation-stripped, suffix-free form for similarity
    comparison. This form is NEVER stored or displayed — only used for matching.

    Examples:
      "TechNova Corporation" → "technova"
      "TechNova Corp."       → "technova"
      "TechNova"             → "technova"
      "Stellar Systems Inc." → "stellar systems"
      "Stellar Systems"      → "stellar systems"
      "Dr. Elena Vasquez"    → "elena vasquez"
      "Elena Vasquez"        → "elena vasquez"
      "Apache Kafka"         → "apache kafka"    (no suffixes to strip)
    """
    # Unicode composition (é as single codepoint)
    name = unicodedata.normalize("NFC", name)

    # Lowercase
    name = name.lower()

    # Remove punctuation except internal hyphens
    # e.g. "TechNova Corp." → "technova corp"
    name = re.sub(r"[.,!?;:()\[\]\"']+", "", name)

    # Tokenize
    tokens = name.split()

    # Strip leading honorifics (person names only, but safe for all types)
    if tokens and tokens[0] in _HONORIFICS:
        tokens = tokens[1:]

    # Strip trailing legal suffixes
    # Strip from the end so "Co" in "Cisco" isn't removed
    while tokens and tokens[-1] in _LEGAL_SUFFIXES:
        tokens = tokens[:-1]

    # If we stripped everything, fall back to original tokenization
    if not tokens:
        tokens = name.split()

    return " ".join(tokens)


def canonical_sort_key(name: str, mention_count: int) -> tuple:
    """
    Sort key for picking the canonical name from a cluster.

    Primary:   mention_count descending (most-mentioned name wins)
    Secondary: token count descending (longer / more complete name wins)
    Tertiary:  name ascending (alphabetic tiebreaker for determinism)
    """
    return (-mention_count, -len(name.split()), name.lower())
