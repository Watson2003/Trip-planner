from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import dataclasses
import types
import typing
from typing import Literal

from . import typing_objects

# Pydantic expects this alias from typing-inspection.
Qualifier = Literal["required", "not_required", "read_only", "class_var", "init_var", "final"]

UNKNOWN = object()


class AnnotationSource(Enum):
    ANY = "any"
    CLASS = "class"
    DATACLASS = "dataclass"
    FUNCTION = "function"
    NAMED_TUPLE = "named_tuple"
    TYPED_DICT = "typed_dict"


@dataclass(frozen=True)
class InspectedAnnotation:
    type: object
    qualifiers: set[str]
    metadata: list[object]


class ForbiddenQualifier(ValueError):
    def __init__(self, qualifier: str) -> None:
        super().__init__(qualifier)
        self.qualifier = qualifier


def is_union_origin(origin: object) -> bool:
    return origin is typing.Union or origin is types.UnionType


def get_literal_values(literal: object, *args: object, **kwargs: object) -> tuple[object, ...]:
    del args, kwargs
    if typing_objects.is_literal(literal):
        return typing.get_args(literal)
    return ()


def _extract_qualifier(annotation: object) -> tuple[str | None, object]:
    origin = typing.get_origin(annotation)
    if origin is typing.ClassVar:
        args = typing.get_args(annotation)
        return "class_var", args[0] if args else UNKNOWN
    if origin is typing.Final:
        args = typing.get_args(annotation)
        return "final", args[0] if args else UNKNOWN
    if hasattr(typing, "Required") and origin is typing.Required:
        args = typing.get_args(annotation)
        return "required", args[0] if args else UNKNOWN
    if hasattr(typing, "NotRequired") and origin is typing.NotRequired:
        args = typing.get_args(annotation)
        return "not_required", args[0] if args else UNKNOWN
    if hasattr(typing, "Self") and annotation is typing.Self:
        return "self", annotation
    if hasattr(dataclasses, "InitVar") and origin is dataclasses.InitVar:
        args = typing.get_args(annotation)
        return "init_var", args[0] if args else UNKNOWN
    return None, annotation


def inspect_annotation(
    annotation: object,
    *,
    annotation_source: AnnotationSource = AnnotationSource.ANY,
    unpack_type_aliases: str = "skip",
) -> InspectedAnnotation:
    del annotation_source, unpack_type_aliases

    qualifiers: set[str] = set()
    metadata: list[object] = []
    current = annotation

    while True:
        origin = typing.get_origin(current)
        if typing_objects.is_annotated(origin):
            args = typing.get_args(current)
            if args:
                current = args[0]
                metadata.extend(args[1:])
                continue
        qualifier, stripped = _extract_qualifier(current)
        if qualifier is not None:
            qualifiers.add(qualifier)
            current = stripped
            if current is UNKNOWN:
                break
            continue
        break

    if current is typing.Any:
        current = typing.Any

    return InspectedAnnotation(type=current, qualifiers=qualifiers, metadata=metadata)
