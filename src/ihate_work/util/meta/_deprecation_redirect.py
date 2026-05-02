"""Metaprogramming utilities — PEP 562 deprecation redirects, etc."""

from __future__ import annotations

import importlib
import re
import warnings
from collections.abc import Callable, Sequence

_DATE_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")


def create_redirection_getattr(
    module_name: str,
    redirects: Sequence[tuple[str, str, str] | tuple[str, str, str, str]],
) -> Callable[[str], object]:
    """Build a module-level ``__getattr__`` that redirects old names with a warning.

    Args:
        module_name: The current module's ``__name__`` (for error messages).
        redirects: Each entry is ``(name, new_package, new_name)`` or
            ``(name, new_package, new_name, removal_date)``.
            ``removal_date`` accepts ``YYYY``, ``YYYY-MM``, or ``YYYY-MM-DD``.

    Returns:
        A ``__getattr__`` function to assign at module level.

    Example::

        # old_module.py
        from ihate_work.util.meta import create_redirection_getattr

        __getattr__ = create_redirection_getattr(__name__, [
            ("Foo", "new_package.new_module", "Foo"),
            ("bar", "new_package.new_module", "bar_v2", "2026-06"),
        ])
    """
    lookup: dict[str, tuple[str, str, str | None]] = {}
    for entry in redirects:
        if len(entry) == 3:
            name, new_pkg, new_name = entry
            removal_date = None
        elif len(entry) == 4:
            name, new_pkg, new_name, removal_date = entry
        else:
            raise ValueError(f"redirect entry must be 3- or 4-tuple, got {len(entry)}: {entry!r}")
        if removal_date is not None and not _DATE_RE.fullmatch(removal_date):
            raise ValueError(f"removal_date must match YYYY, YYYY-MM, or YYYY-MM-DD, got {removal_date!r}")
        lookup[name] = (new_pkg, new_name, removal_date)

    def __getattr__(name: str) -> object:
        if name in lookup:
            new_pkg, new_name, removal_date = lookup[name]
            msg = f"{module_name}.{name} has moved to {new_pkg}.{new_name}"
            if removal_date:
                msg += f" — will be removed after {removal_date}"
            warnings.warn(msg, DeprecationWarning, stacklevel=2)
            mod = importlib.import_module(new_pkg)
            return getattr(mod, new_name)
        raise AttributeError(f"module {module_name!r} has no attribute {name!r}")

    return __getattr__
