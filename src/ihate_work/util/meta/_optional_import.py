"""PEP 562 ``__getattr__`` factory for optional-dependency imports.

Lets a package expose names that require optional third-party libraries.
The import only happens when the name is actually accessed, so the package
itself stays importable without the optional dep installed.

Example::

    # ihate_work/util/concurrency/__init__.py
    from ihate_work.util.meta import create_optional_getattr

    __getattr__ = create_optional_getattr(__name__, [
        ("LokyExecutor", "ihate_work.util.concurrency.loky_executor", "loky"),
    ])
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Sequence


def create_optional_getattr(
    module_name: str,
    optionals: Sequence[tuple[str, str] | tuple[str, str, str]],
) -> Callable[[str], object]:
    """Build a module-level ``__getattr__`` for optional-dep lazy imports.

    Args:
        module_name: The current module's ``__name__`` (for error messages).
        optionals: Each entry is ``(attr_name, source_module)`` or
            ``(attr_name, source_module, pip_package)``.

            *attr_name*  — the public name to expose on this module.
            *source_module* — the dotted path to import the attr from.
            *pip_package* — (optional) the pip install name shown in the
                error message.  Defaults to the top-level package of
                *source_module* (i.e. everything before the first dot).

    Returns:
        A ``__getattr__`` function to assign at module level.

    Raises:
        ImportError: When the optional dependency is not installed and
            the attribute is accessed.
        AttributeError: For names not in *optionals*.
    """
    lookup: dict[str, tuple[str, str]] = {}
    for entry in optionals:
        if len(entry) == 2:
            attr_name, source_mod = entry
            pip_pkg = source_mod.split(".")[0]
        elif len(entry) == 3:
            attr_name, source_mod, pip_pkg = entry
        else:
            raise ValueError(f"optional entry must be a 2- or 3-tuple, got {len(entry)}: {entry!r}")
        lookup[attr_name] = (source_mod, pip_pkg)

    def __getattr__(name: str) -> object:
        if name in lookup:
            source_mod, pip_pkg = lookup[name]
            try:
                mod = importlib.import_module(source_mod)
            except ImportError as exc:
                raise ImportError(
                    f"{module_name}.{name} requires the '{pip_pkg}' package. Install it with:  pip install {pip_pkg}"
                ) from exc
            return getattr(mod, name)
        raise AttributeError(f"module {module_name!r} has no attribute {name!r}")

    return __getattr__
