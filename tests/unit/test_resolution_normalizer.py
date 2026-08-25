"""
Tests for src/resolution/normalizer.py

Key invariants:
  - Legal suffixes are stripped; descriptive words are NOT
  - Leading honorifics are stripped from person names
  - Normalized form is lowercase and punctuation-free
  - Stripping everything falls back to original tokens
  - canonical_sort_key: mention-count descends, length descends, alpha ascends
"""

import pytest

from src.resolution.normalizer import canonical_sort_key, normalize_for_comparison


class TestNormalizeForComparison:
    # ── Company names with legal suffixes ─────────────────────────────────────

    def test_corporation_stripped(self):
        assert normalize_for_comparison("TechNova Corporation") == "technova"

    def test_corp_abbreviated_stripped(self):
        assert normalize_for_comparison("TechNova Corp") == "technova"

    def test_corp_with_period_stripped(self):
        assert normalize_for_comparison("TechNova Corp.") == "technova"

    def test_inc_stripped(self):
        assert normalize_for_comparison("Stellar Systems Inc.") == "stellar systems"

    def test_inc_no_period_stripped(self):
        assert normalize_for_comparison("Stellar Systems Inc") == "stellar systems"

    def test_ltd_stripped(self):
        assert normalize_for_comparison("Acme Ltd") == "acme"

    def test_llc_stripped(self):
        assert normalize_for_comparison("DataOps LLC") == "dataops"

    # ── Descriptive words NOT stripped ────────────────────────────────────────

    def test_systems_not_stripped(self):
        assert normalize_for_comparison("Stellar Systems") == "stellar systems"

    def test_analytics_not_stripped(self):
        assert normalize_for_comparison("Apex Analytics") == "apex analytics"

    def test_technologies_not_stripped(self):
        assert normalize_for_comparison("Global Technologies") == "global technologies"

    # ── Three variants converge to same normalized form ───────────────────────

    def test_technova_variants_all_equal(self):
        results = {
            normalize_for_comparison("TechNova Corporation"),
            normalize_for_comparison("TechNova Corp"),
            normalize_for_comparison("TechNova"),
        }
        assert len(results) == 1

    def test_stellar_variants_all_equal(self):
        results = {
            normalize_for_comparison("Stellar Systems Inc."),
            normalize_for_comparison("Stellar Systems"),
        }
        assert len(results) == 1

    # ── Person names with honorifics ──────────────────────────────────────────

    def test_dr_stripped(self):
        assert normalize_for_comparison("Dr. Elena Vasquez") == "elena vasquez"

    def test_professor_stripped(self):
        assert normalize_for_comparison("Professor James Okafor") == "james okafor"

    def test_no_honorific_unchanged(self):
        assert normalize_for_comparison("Aisha Patel") == "aisha patel"

    # ── Technologies — no suffixes to strip ──────────────────────────────────

    def test_apache_kafka_unchanged(self):
        assert normalize_for_comparison("Apache Kafka") == "apache kafka"

    def test_kubernetes_unchanged(self):
        assert normalize_for_comparison("Kubernetes") == "kubernetes"

    # ── Casing and punctuation ────────────────────────────────────────────────

    def test_lowercase(self):
        result = normalize_for_comparison("ACME CORPORATION")
        assert result == result.lower()

    def test_trailing_punctuation_removed(self):
        assert normalize_for_comparison("DataBridge.") == "databridge"

    def test_parens_removed(self):
        assert normalize_for_comparison("DataBridge (ETL)") == "databridge etl"

    # ── Edge case: stripping everything falls back to original ────────────────

    def test_single_legal_suffix_word_not_empty(self):
        # "Corp" alone → we strip "corp" → empty → fall back → "corp"
        result = normalize_for_comparison("Corp")
        assert result  # must not be empty string


class TestCanonicalSortKey:
    def test_higher_mention_count_sorts_first(self):
        # More mentions → smaller sort key → comes first when sorted ascending
        key_popular = canonical_sort_key("TechNova Corporation", 5)
        key_rare = canonical_sort_key("TechNova Corp", 1)
        assert key_popular < key_rare

    def test_longer_name_wins_on_tie(self):
        # Same mention count → longer name sorts first
        key_long = canonical_sort_key("TechNova Corporation", 2)
        key_short = canonical_sort_key("TechNova", 2)
        assert key_long < key_short

    def test_alphabetic_tiebreaker(self):
        # Same count and same length → alphabetically earlier wins
        key_a = canonical_sort_key("Apex Corp", 1)
        key_b = canonical_sort_key("Beta Corp", 1)
        assert key_a < key_b

    def test_returns_tuple(self):
        assert isinstance(canonical_sort_key("Test", 3), tuple)
        assert len(canonical_sort_key("Test", 3)) == 3
