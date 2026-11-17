from agentbench.evaluation import Evaluator, register
from collections import Counter

def calculate_scores(output, expected):
    output_tokens = output.split()
    expected_tokens = expected.split()

    output_count = Counter(output_tokens)
    expected_count = Counter(expected_tokens)

    overlap = sum(
        (output_count & expected_count).values()
    )

    output_len = len(output_tokens)
    expected_len = len(expected_tokens)

    if output_len == 0 and expected_len == 0:
        return {
            "overlap": 0,
            "precision": 1.0,
            "recall": 1.0,
            "f1": 1.0
        }

    if output_len == 0 or expected_len == 0:
        return {
            "overlap": 0,
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0
        }

    precision = overlap / output_len
    recall = overlap / expected_len

    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall > 0
        else 0.0
    )

    return {
        "overlap": overlap,
        "precision": precision,
        "recall": recall,
        "f1": f1
    }


@register("tokenf1")
class TokenF1(Evaluator):
    def __init__(self, expected_key="answer",output_key=None, **kw):
        super().__init__(**kw)
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
        
        scores = calculate_scores(actual, expected)
        value = scores['f1']
        
        return self.result(value, scores=scores)

