from __future__ import annotations

import difflib
from typing import Any, Callable, Iterable, Union

from .evaluator import Evaluator

_REGISTRY: dict[str, type[Evaluator]] = {}

EvaluatorSpec = Union[str, dict, Evaluator]


class UnknownEvaluatorError(LookupError):
    pass


def register(name: str) -> Callable[[type[Evaluator]], type[Evaluator]]:
    """Class decorator:  @register("exact_match")"""

    def decorator(cls: type[Evaluator]) -> type[Evaluator]:
        
        if not (isinstance(cls, type) and issubclass(cls, Evaluator)):
            raise TypeError("@register can only be used on Evaluator subclasses")
        
        existing = _REGISTRY.get(name)
        if existing is not None and (existing.__module__, existing.__qualname__) != (cls.__module__, cls.__qualname__,):
            raise ValueError(f"evaluator name {name!r} is already taken by {existing.__qualname__}")

        cls.name = name
        _REGISTRY[name] = cls
        return cls

    return decorator


def list_evaluators() -> list[str]:
    return sorted(_REGISTRY)


def get_evaluator(name: str, /, **options: Any) -> Evaluator:
   
    try:
        cls = _REGISTRY[name]
    except KeyError:
        close = difflib.get_close_matches(name, _REGISTRY, n=1)
        hint = f" Did you mean {close[0]!r}?" if close else ""
        raise UnknownEvaluatorError(f"unknown evaluator {name!r}.{hint} Available: {list_evaluators()}") from None
    
    try:
        return cls(**options)
    except TypeError as e: 
        raise TypeError(f"evaluator {name!r}: {e}") from e


def build_evaluators(specs: Iterable[EvaluatorSpec]) -> list[Evaluator]:

    built: list[Evaluator] = []
    for spec in specs:
        if isinstance(spec, Evaluator):
            built.append(spec)
        elif isinstance(spec, str):
            built.append(get_evaluator(spec))
        elif isinstance(spec, dict):
            options = dict(spec)  # don't modify the caller's config
            if "type" not in options:
                raise ValueError(f'evaluator spec {spec!r} needs a "type" key')
            built.append(get_evaluator(options.pop("type"), **options))
        else:
            raise TypeError(f"evaluator spec must be a name, dict or Evaluator, got {type(spec).__name__}")
    names = [e.name for e in built]
    dupes = sorted({n for n in names if names.count(n) > 1})
    if dupes:
        raise ValueError(f"duplicate evaluator name(s) {dupes}: give each one a unique name=...")
    return built