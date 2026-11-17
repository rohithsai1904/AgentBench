from agentbench.evaluation import Evaluator, register

_MISSING = object()          # "key not there" is different from "key is there and is None"


def get_path(data, path):
    """get_path({"refund": {"amount": 5}}, "refund.amount") -> 5, or _MISSING."""
    current = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, (list, tuple)) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return _MISSING
    return current


def values_match(actual, expected, tolerance=0.0):
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected   # in Python, 1 == True
    is_number = lambda v: isinstance(v, (int, float))
    if is_number(actual) and is_number(expected):
        return abs(actual - expected) <= tolerance
    return actual == expected


@register("field_match")
class FieldMatch(Evaluator):
    def __init__(self, fields=None, expected_key="fields", tolerance=0.0, required=False, **kw):
        super().__init__(**kw)
        self.fields = fields                  # None = every path listed in the expectation
        self.expected_key = expected_key      # case.expectations[expected_key] = {"path": expected_value}
        self.tolerance = tolerance
        self.required = required              # True: any missing field makes the whole score 0

    async def score(self, case, output):                      # note the order: case, THEN output
        expected = (case.expectations or {}).get(self.expected_key)
        if not expected:
            return self.skipped(f"case has no {self.expected_key!r} expectation")
        
        paths = [p for p in expected if self.fields is None or p in self.fields]
        if not paths:
            return self.skipped("none of the requested fields are in the expectation")
        if not isinstance(output, (dict, list, tuple)):
            return self.result(0.0, f"output is {type(output).__name__}, not a dict", mismatched=paths)

        matched, mismatched, missing = [], [], []
        for path in paths:
            actual = get_path(output, path)
            if actual is _MISSING:
                missing.append(path)
                mismatched.append(path)
            elif values_match(actual, expected[path], self.tolerance):
                matched.append(path)
            else:
                mismatched.append(f"{path} (expected {expected[path]!r}, got {actual!r})")

        if self.required and missing:
            return self.result(0.0, f"missing required field(s): {', '.join(missing)}",
                               matched=matched, mismatched=mismatched, missing=missing)
        value = len(matched) / len(paths)
        reason = f"{len(matched)}/{len(paths)} fields match"
        if mismatched:
            reason += "; wrong: " + ", ".join(mismatched)
        return self.result(value, reason, matched=matched, mismatched=mismatched, missing=missing)