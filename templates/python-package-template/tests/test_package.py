"""Verify package metadata and import correctness."""
from __future__ import annotations

import mypkg


def test_version_is_string() -> None:
    assert isinstance(mypkg.__version__, str)


def test_version_format() -> None:
    parts = mypkg.__version__.split(".")
    assert len(parts) == 3  # noqa: PLR2004
    assert all(part.isdigit() for part in parts)
