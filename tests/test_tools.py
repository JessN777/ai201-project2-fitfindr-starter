"""
tests/test_tools.py

Pytest tests for the three FitFindr tools.
Each tool has tests for its happy path and at least one test per failure mode.

Run with:
    pytest tests/

Note: suggest_outfit and create_fit_card require GROQ_API_KEY in .env.
Tests that call the LLM are marked with @pytest.mark.integration and can be
skipped in CI without an API key: pytest tests/ -m "not integration"
"""

import os
import pytest

# ── search_listings tests ─────────────────────────────────────────────────────
# These tests require no API key — search_listings is pure Python.

from tools import search_listings


class TestSearchListings:

    def test_returns_list(self):
        """Happy path: returns a list of dicts."""
        results = search_listings("vintage graphic tee", size=None, max_price=50)
        assert isinstance(results, list)

    def test_happy_path_returns_results(self):
        """Common query should find at least one listing."""
        results = search_listings("vintage graphic tee", size=None, max_price=50)
        assert len(results) > 0

    def test_results_have_required_fields(self):
        """Every returned listing must have all standard fields."""
        results = search_listings("jacket", size=None, max_price=200)
        required = {"id", "title", "description", "category", "style_tags",
                    "size", "condition", "price", "colors", "platform"}
        for item in results:
            assert required.issubset(item.keys()), (
                f"Listing {item.get('id')} missing fields: {required - item.keys()}"
            )

    def test_price_filter(self):
        """All returned listings must be at or below max_price."""
        results = search_listings("jacket", size=None, max_price=30)
        assert all(item["price"] <= 30 for item in results), (
            "search_listings returned items above max_price"
        )

    def test_size_filter(self):
        """Returned listings must match the requested size."""
        results = search_listings("top", size="S", max_price=9999)
        for item in results:
            size_str = item.get("size", "").lower()
            assert "s" in size_str or "one size" in size_str, (
                f"Size mismatch: listing size '{item['size']}' doesn't contain 'S'"
            )

    # ── Failure mode 1: no matches ────────────────────────────────────────────

    def test_no_results_returns_empty_list(self):
        """Impossible query should return [] not raise an exception."""
        results = search_listings("designer ballgown", size="XXS", max_price=5)
        assert results == [], f"Expected [], got {results}"

    def test_no_results_does_not_raise(self):
        """search_listings must never raise, even with a nonsense query."""
        try:
            results = search_listings("xyzzy impossible foobar", size=None, max_price=0.01)
            assert isinstance(results, list)
        except Exception as exc:
            pytest.fail(f"search_listings raised an exception on no-match: {exc}")

    def test_returns_at_most_six_results(self):
        """Results are capped at 6."""
        results = search_listings("vintage", size=None, max_price=9999)
        assert len(results) <= 6

    # ── Failure mode 2: file/data error ──────────────────────────────────────

    def test_invalid_max_price_zero(self):
        """max_price=0 should return [] (all items cost > 0), not crash."""
        results = search_listings("tee", size=None, max_price=0)
        assert isinstance(results, list)

    def test_empty_description_with_filters(self):
        """Empty description should still apply price/size filters without crashing."""
        results = search_listings("", size=None, max_price=20)
        assert isinstance(results, list)
        assert all(item["price"] <= 20 for item in results)


# ── suggest_outfit tests ──────────────────────────────────────────────────────

from tools import suggest_outfit
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


class TestSuggestOutfit:

    @pytest.fixture
    def sample_item(self):
        """A realistic listing dict to use as new_item."""
        results = search_listings("vintage graphic tee", size=None, max_price=50)
        assert results, "Need at least one listing for this test"
        return results[0]

    # ── Failure mode 1: empty wardrobe ────────────────────────────────────────

    @pytest.mark.integration
    def test_empty_wardrobe_returns_string(self, sample_item):
        """Empty wardrobe must return a non-empty string (not crash or return '')."""
        result = suggest_outfit(sample_item, get_empty_wardrobe())
        assert isinstance(result, str), "suggest_outfit must return a string"
        assert result.strip() != "", "suggest_outfit returned empty string for empty wardrobe"

    @pytest.mark.integration
    def test_empty_wardrobe_does_not_raise(self, sample_item):
        """suggest_outfit must never raise, even with an empty wardrobe."""
        try:
            result = suggest_outfit(sample_item, get_empty_wardrobe())
            assert isinstance(result, str)
        except Exception as exc:
            pytest.fail(f"suggest_outfit raised with empty wardrobe: {exc}")

    # ── Happy path ────────────────────────────────────────────────────────────

    @pytest.mark.integration
    def test_example_wardrobe_returns_string(self, sample_item):
        """With a populated wardrobe, returns a non-empty string."""
        result = suggest_outfit(sample_item, get_example_wardrobe())
        assert isinstance(result, str)
        assert result.strip() != ""

    @pytest.mark.integration
    def test_result_mentions_item(self, sample_item):
        """The outfit suggestion should reference the item in some way."""
        result = suggest_outfit(sample_item, get_example_wardrobe())
        # At minimum, something about the item name or category should appear
        item_words = set(
            (sample_item.get("title", "") + " " + sample_item.get("category", "")).lower().split()
        )
        result_lower = result.lower()
        assert any(word in result_lower for word in item_words if len(word) > 3), (
            f"suggest_outfit result doesn't seem to reference the item at all:\n{result}"
        )

    # ── Failure mode 2: missing API key (no integration marker) ──────────────

    def test_no_api_key_returns_fallback(self, sample_item, monkeypatch):
        """If GROQ_API_KEY is missing, suggest_outfit returns a fallback string."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        result = suggest_outfit(sample_item, get_example_wardrobe())
        assert isinstance(result, str), "Must return a string even without API key"
        assert result.strip() != "", "Must return a non-empty fallback string"


# ── create_fit_card tests ─────────────────────────────────────────────────────

from tools import create_fit_card


class TestCreateFitCard:

    @pytest.fixture
    def sample_item(self):
        results = search_listings("vintage graphic tee", size=None, max_price=50)
        assert results
        return results[0]

    @pytest.fixture
    def sample_outfit(self):
        return (
            "Outfit 1 — Off-Duty Grunge:\n"
            "Pieces: Graphic tee, baggy dark-wash jeans, black combat boots, black crossbody bag\n"
            "Vibe: Grungy-cool without trying.\n"
            "Tip: Leave the tee untucked and slightly cropped over the waistband."
        )

    # ── Failure mode 1: empty outfit string ───────────────────────────────────

    def test_empty_outfit_returns_string(self, sample_item):
        """Empty outfit string must return a fallback caption, not raise."""
        result = create_fit_card("", sample_item)
        assert isinstance(result, str), "Must return a string"
        assert result.strip() != "", "Must return a non-empty fallback string"

    def test_empty_outfit_does_not_raise(self, sample_item):
        """create_fit_card must never raise, even with an empty outfit."""
        try:
            result = create_fit_card("", sample_item)
            assert isinstance(result, str)
        except Exception as exc:
            pytest.fail(f"create_fit_card raised with empty outfit: {exc}")

    def test_whitespace_only_outfit_returns_string(self, sample_item):
        """Whitespace-only outfit is treated the same as empty."""
        result = create_fit_card("   \n\t  ", sample_item)
        assert isinstance(result, str)
        assert result.strip() != ""

    # ── Happy path ────────────────────────────────────────────────────────────

    @pytest.mark.integration
    def test_happy_path_returns_string(self, sample_outfit, sample_item):
        """Valid inputs should produce a non-empty caption string."""
        result = create_fit_card(sample_outfit, sample_item)
        assert isinstance(result, str)
        assert result.strip() != ""

    @pytest.mark.integration
    def test_caption_contains_hashtags(self, sample_outfit, sample_item):
        """Caption should include at least one hashtag."""
        result = create_fit_card(sample_outfit, sample_item)
        assert "#" in result, f"Expected hashtags in caption, got:\n{result}"

    @pytest.mark.integration
    def test_varied_output(self, sample_outfit, sample_item):
        """Two calls with the same input should (usually) produce different output."""
        result1 = create_fit_card(sample_outfit, sample_item)
        result2 = create_fit_card(sample_outfit, sample_item)
        # High temperature means outputs should vary — this isn't guaranteed
        # but two identical 50+ character strings would be suspicious
        if len(result1) > 50 and len(result2) > 50:
            assert result1 != result2, (
                "create_fit_card returned identical output twice — "
                "check that temperature > 0 in the LLM call."
            )

    # ── Failure mode 2: missing API key ──────────────────────────────────────

    def test_no_api_key_returns_fallback(self, sample_outfit, sample_item, monkeypatch):
        """If GROQ_API_KEY is missing, returns a fallback caption string."""
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        result = create_fit_card(sample_outfit, sample_item)
        assert isinstance(result, str)
        assert result.strip() != ""
