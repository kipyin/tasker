"""Category string merge (Outlook)."""

from __future__ import annotations

from tasker.infrastructure.outlook.category_util import merge_category_strings


def test_merge_category_strings() -> None:
    assert merge_category_strings("A; B", "C; A") == "A; B; C"
    assert merge_category_strings("", "Z") == "Z"
    assert merge_category_strings("  a  ; b  ", "  b  ; c") == "a; b; c"
