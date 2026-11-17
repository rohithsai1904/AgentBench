import math

from agentbench.evaluation import Evaluator, register
from agentbench.evaluation.evaluator.embedder import HashingEmbedder


def cosine(a: list[float], b: list[float]) -> float:

    if len(a) != len(b):
        raise ValueError("Vectors must have the same dimensions")

    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


@register("similarity")
class Similarity(Evaluator):
    def __init__(self, expected_key="answer",output_key=None, **kw):
        super().__init__(**kw)
        self.expected_key = expected_key
        self.output_key = output_key
    
    async def score(self, case, output):
        embedder = HashingEmbedder(256)

        expected = (case.expectations or {}).get(self.expected_key)
        if expected is None:
            return self.skipped(f"case has no {self.expected_key!r} expectation")
        
        actual = output
        if self.output_key is not None:
            if not isinstance(output, dict) or self.output_key not in output:
                return self.result(0.0, f"output has no {self.output_key!r} field")
            actual = output[self.output_key]
        
        vectors = embedder.embed([expected,actual])

        value = cosine(vectors[0],vectors[1])

        return self.result(value)


