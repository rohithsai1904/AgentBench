def _get(obj, name):
    """Read a field from a dict OR from an object. Returns None if it isn't there."""
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def extract_usage(result):
    attrs = {}
    usage = _get(result, "usage")

    # Anthropic calls them input/output, OpenAI calls them prompt/completion
    input_tokens = _get(usage, "input_tokens")
    if input_tokens is None:
        input_tokens = _get(usage, "prompt_tokens")

    output_tokens = _get(usage, "output_tokens")
    if output_tokens is None:
        output_tokens = _get(usage, "completion_tokens")

    if isinstance(input_tokens, int):
        attrs["llm.input_tokens"] = input_tokens
    if isinstance(output_tokens, int):
        attrs["llm.output_tokens"] = output_tokens

    total = _get(usage, "total_tokens")
    if isinstance(total, int):
        attrs["llm.total_tokens"] = total
    elif isinstance(input_tokens, int) and isinstance(output_tokens, int):
        attrs["llm.total_tokens"] = input_tokens + output_tokens

    model = _get(result, "model")
    if isinstance(model, str):
        attrs["llm.model"] = model

    return attrs