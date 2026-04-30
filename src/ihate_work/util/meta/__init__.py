"""Metaprogramming utilities — PEP 562 module ``__getattr__`` factories."""

from ihate_work.util.meta._deprecation_redirect import create_redirection_getattr
from ihate_work.util.meta._optional_import import create_optional_getattr

__all__ = ["create_optional_getattr", "create_redirection_getattr"]
