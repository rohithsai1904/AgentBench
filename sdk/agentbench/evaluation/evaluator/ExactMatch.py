from agentbench.evaluation import Evaluator, register


def normalize(text, *, case_sensitive=False, strip=True, normalize_whitespace=True) -> str:
    """Turn any value into comparable text. Other evaluators can reuse this later."""
    text = "" if text is None else str(text)
    if strip:
        text = text.strip()
    if normalize_whitespace:
        text = " ".join(text.split())        # "a   b\n c" -> "a b c"
    if not case_sensitive:
        text = text.lower()
    return text


@register("exact_match")
class ExactMatch(Evaluator):
    def __init__(self, case_sensitive=False, strip=True, normalize_whitespace=True,
                 expected_key="answer", output_key=None, **kw):
        super().__init__(**kw)               # always call this
        self.case_sensitive = case_sensitive
        self.strip = strip
        self.normalize_whitespace = normalize_whitespace
        self.expected_key = expected_key     # which key of case.expectations holds the answer
        self.output_key = output_key         # None = whole output; "reply" = output["reply"]

    async def score(self, case, output):
        expected = (case.expectations or {}).get(self.expected_key)
        if expected is None:
            return self.skipped(f"case has no {self.expected_key!r} expectation")

        actual = output
        if self.output_key is not None:
            if not isinstance(output, dict) or self.output_key not in output:
                return self.result(0.0, f"output has no {self.output_key!r} field")
            actual = output[self.output_key]

        opts = dict(case_sensitive=self.case_sensitive, strip=self.strip,
                    normalize_whitespace=self.normalize_whitespace)
        a, e = normalize(actual, **opts), normalize(expected, **opts)
        if a == e:
            return self.result(1.0, "exact match")
        return self.result(0.0, f"expected {e!r}, got {a!r}")