"""Tests for create_optional_getattr."""

from __future__ import annotations

import types

import pytest

from ihate_work.util.meta import create_optional_getattr


def _make_module(name: str, optionals):
    mod = types.ModuleType(name)
    mod.__getattr__ = create_optional_getattr(name, optionals)
    return mod


def test_resolves_installed_package():
    """Accessing an attr backed by an installed package works."""
    mod = _make_module(
        "my_pkg",
        [
            ("sep", "os"),
        ],
    )
    assert mod.sep is not None
    assert isinstance(mod.sep, str)


def test_import_error_for_missing_package():
    """Accessing an attr whose dep is missing raises ImportError."""
    mod = _make_module(
        "my_pkg",
        [
            ("Widget", "nonexistent_pkg_abc123.widgets"),
        ],
    )
    with pytest.raises(ImportError, match="requires the 'nonexistent_pkg_abc123' package"):
        mod.Widget


def test_import_error_with_custom_pip_name():
    """The pip_package override appears in the error message."""
    mod = _make_module(
        "my_pkg",
        [
            ("Widget", "nonexistent_pkg_abc123.widgets", "cool-widgets"),
        ],
    )
    with pytest.raises(ImportError, match="pip install cool-widgets"):
        mod.Widget


def test_attribute_error_for_unknown():
    mod = _make_module(
        "my_pkg",
        [
            ("path", "os.path"),
        ],
    )
    with pytest.raises(AttributeError, match="no attribute 'nope'"):
        mod.nope


def test_bad_tuple_length():
    with pytest.raises(ValueError, match="2- or 3-tuple"):
        create_optional_getattr("m", [("a",)])
    with pytest.raises(ValueError, match="2- or 3-tuple"):
        create_optional_getattr("m", [("a", "b", "c", "d")])


def test_default_pip_package_from_source():
    """When pip_package is omitted, it's inferred from source_module."""
    mod = _make_module(
        "my_pkg",
        [
            ("Widget", "nonexistent_xyz.sub.mod"),
        ],
    )
    with pytest.raises(ImportError, match="pip install nonexistent_xyz"):
        mod.Widget
