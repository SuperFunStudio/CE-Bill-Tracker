"""Pre-filing docket shells — the rule that keeps MA/KY duplicates out of the corpus.

Every identifier below is a real corpus row. The distinction the rule has to get right: HD-3107 with
no action is a shell that duplicates H-988, while HD-2793 sitting at passed_chamber with a real date is
a bill the House is genuinely moving under that docket number. A prefix-only rule would shed both.
"""
import datetime

import pytest

from app.ingestion.docket import is_docket_shell


def d(s: str) -> datetime.date:
    return datetime.date.fromisoformat(s)


class TestShells:
    @pytest.mark.parametrize("state,number", [
        ("MA", "HD-3107"),   # -> filed as H-988 (mattress recycling)
        ("MA", "HD-2145"),   # -> H-979 / S-653 / … (electronics producer responsibility)
        ("MA", "SD-2101"),   # -> S-569 (mattress stewardship)
        ("MA", "SD-199"),    # -> S-166 (digital right to repair)
        ("KY", "BR-342"),    # bill request, never referred
        ("KY", "BR-434"),
    ])
    def test_actionless_docket_number_is_a_shell(self, state, number):
        assert is_docket_shell(state, number, None) is True

    def test_case_and_whitespace_tolerated(self):
        assert is_docket_shell("ma", " hd-3107 ", None) is True


class TestNotShells:
    """The false positives a blanket prefix match would cause."""

    @pytest.mark.parametrize("state,number,last_action", [
        ("MA", "HD-2793", "2025-02-27"),  # passed_chamber — real activity under the docket number
        ("MA", "SD-732", "2025-02-27"),
        ("MA", "HD-6020", "2026-04-08"),  # in_committee
    ])
    def test_docket_number_with_recorded_action_is_kept(self, state, number, last_action):
        assert is_docket_shell(state, number, d(last_action)) is False

    @pytest.mark.parametrize("state,number", [
        ("MA", "H-988"),     # the filed bill itself
        ("MA", "S-569"),
        ("CA", "SB-244"),
        ("CA", "AB-1201"),
    ])
    def test_ordinary_bill_number_is_never_a_shell(self, state, number):
        assert is_docket_shell(state, number, None) is False

    def test_prefix_is_scoped_to_the_issuing_state(self):
        """SD-2101 is a Massachusetts Senate Docket; in South Dakota it would be a real bill series."""
        assert is_docket_shell("SD", "SD-2101", None) is False
        assert is_docket_shell("VA", "HD-3107", None) is False

    @pytest.mark.parametrize("number", ["HD", "HD-", "HDX-12", "HD-12A", "AHD-12", ""])
    def test_near_miss_identifiers_are_not_shells(self, number):
        assert is_docket_shell("MA", number, None) is False

    def test_missing_fields_are_not_shells(self):
        assert is_docket_shell(None, None, None) is False
