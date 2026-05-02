import types
import warnings

import pytest

from ihate_work.util.meta import create_redirection_getattr


def _make_module(name: str, redirects):
    """Create a fake module with __getattr__ installed."""
    mod = types.ModuleType(name)
    mod.__getattr__ = create_redirection_getattr(name, redirects)
    return mod


def test_redirect_resolves():
    mod = _make_module(
        "old_pkg",
        [
            ("Rater", "ihate_work.util.perf.rater", "Rater"),
        ],
    )
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        cls = mod.Rater
    assert cls.__name__ == "Rater"
    assert len(w) == 1
    assert issubclass(w[0].category, DeprecationWarning)
    assert "old_pkg.Rater has moved to ihate_work.util.perf.rater.Rater" in str(w[0].message)


def test_removal_date_in_message():
    mod = _make_module(
        "old_pkg",
        [
            ("Rater", "ihate_work.util.perf.rater", "Rater", "2026-06"),
        ],
    )
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        mod.Rater
    assert "will be removed after 2026-06" in str(w[0].message)


def test_missing_attr_raises():
    mod = _make_module(
        "old_pkg",
        [
            ("Rater", "ihate_work.util.perf.rater", "Rater"),
        ],
    )
    with pytest.raises(AttributeError, match="no attribute 'Nope'"):
        mod.Nope


def test_valid_date_formats():
    for date in ("2026", "2026-06", "2026-06-15"):
        create_redirection_getattr("m", [("X", "os", "path", date)])


def test_invalid_date_rejected():
    for bad in ("26", "2026/06", "2026-6", "2026-06-1", "next year", ""):
        with pytest.raises(ValueError, match="removal_date"):
            create_redirection_getattr("m", [("X", "os", "path", bad)])


def test_bad_tuple_length():
    with pytest.raises(ValueError, match="3- or 4-tuple"):
        create_redirection_getattr("m", [("a", "b")])
    with pytest.raises(ValueError, match="3- or 4-tuple"):
        create_redirection_getattr("m", [("a", "b", "c", "d", "e")])
