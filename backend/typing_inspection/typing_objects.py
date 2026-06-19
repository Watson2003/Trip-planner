from __future__ import annotations

import dataclasses
import types
import typing
from typing import Any

try:
    from typing import TypeAliasType  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    TypeAliasType = type("TypeAliasType", (), {})  # type: ignore[misc,assignment]

try:
    from typing import NoReturn, Never, Self
except ImportError:  # pragma: no cover
    NoReturn = typing.NoReturn
    Never = getattr(typing, "Never", object())
    Self = getattr(typing, "Self", object())

try:
    from typing import Required, NotRequired, ReadOnly
except ImportError:  # pragma: no cover
    Required = getattr(typing, "Required", object())
    NotRequired = getattr(typing, "NotRequired", object())
    ReadOnly = getattr(typing, "ReadOnly", object())


def _origin(tp: object) -> object:
    return typing.get_origin(tp)


def is_annotated(tp: object) -> bool:
    return tp is typing.Annotated or _origin(tp) is typing.Annotated


def is_any(tp: object) -> bool:
    return tp is Any or tp is typing.Any


def is_classvar(tp: object) -> bool:
    return tp is typing.ClassVar or _origin(tp) is typing.ClassVar


def is_deprecated(tp: object) -> bool:
    return getattr(tp, "__deprecated__", False) is not False or tp.__class__.__name__ == "deprecated"


def is_literal(tp: object) -> bool:
    return tp is typing.Literal or _origin(tp) is typing.Literal


def is_never(tp: object) -> bool:
    return tp is Never or _origin(tp) is Never


def is_newtype(tp: object) -> bool:
    return hasattr(tp, "__supertype__")


def is_noextraitems(tp: object) -> bool:
    return False


def is_noreturn(tp: object) -> bool:
    return tp is NoReturn or _origin(tp) is NoReturn


def is_self(tp: object) -> bool:
    return tp is Self or _origin(tp) is Self


def is_typealiastype(tp: object) -> bool:
    return isinstance(tp, TypeAliasType)


def is_typevar(tp: object) -> bool:
    return isinstance(tp, typing.TypeVar) or type(tp).__name__ == "TypeVar"


def is_union(tp: object) -> bool:
    return tp is typing.Union or tp is types.UnionType or _origin(tp) is typing.Union or _origin(tp) is types.UnionType


def is_unpack(tp: object) -> bool:
    return tp is typing.Unpack or _origin(tp) is typing.Unpack
