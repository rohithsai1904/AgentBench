from __future__ import annotations

import functools
import inspect
from typing import Any

from .llm_info import extract_usage       # your Step 1 function
from .tracing import span, to_jsonable

_MARK = "_agentbench_wrapped"


def _input_of(args: tuple, kwargs: dict) -> Any:
    # LLM SDKs take keyword arguments (model=..., messages=...). Keep any positional ones too.
    return to_jsonable({"args": list(args), **kwargs} if args else kwargs)


def _wrap_method(owner: Any, attr: str, span_name: str) -> None:
    """Replace owner.<attr> with a version that records an llm span around each call."""
    
    original = getattr(owner, attr)
    
    if getattr(original, _MARK, False):
        return  # already wrapped: instrumenting twice must not make two spans per call

    if inspect.iscoroutinefunction(original):

        @functools.wraps(original)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            with span(span_name, "llm") as s:
                s.input = _input_of(args, kwargs)
                result = await original(*args, **kwargs)
                s.output = to_jsonable(result)
                s.attributes.update(extract_usage(result))
                return result

    else:

        @functools.wraps(original)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with span(span_name, "llm") as s:
                s.input = _input_of(args, kwargs)
                result = original(*args, **kwargs)
                s.output = to_jsonable(result)
                s.attributes.update(extract_usage(result))
                return result

    setattr(wrapper, _MARK, True)
    setattr(owner, attr, wrapper)  # the swap


def instrument_anthropic(client: Any) -> Any:
    _wrap_method(client.messages, "create", "anthropic.messages.create")
    return client


def instrument_openai(client: Any) -> Any:
    _wrap_method(client.chat.completions, "create", "openai.chat.completions.create")
    return client