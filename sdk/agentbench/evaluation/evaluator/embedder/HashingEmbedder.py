import hashlib
import math

from .Embedder import Embedder


class HashingEmbedder(Embedder):

    def __init__(self, dimensions: int = 128):
        if dimensions <= 0:
            raise ValueError("Dimensions must be positive")

        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:

        vectors = []

        for text in texts:

            vector = [0.0] * self.dimensions

            words = text.lower().split()

            for word in words:

                hash_value = hashlib.sha256(word.encode("utf-8")).digest()
                
                index = int.from_bytes(hash_value[:8], byteorder="big") % self.dimensions
                
                vector[index] += 1.0

            
            norm = math.sqrt(sum(value * value for value in vector))

            if norm > 0:
                vector = [value / norm for value in vector]

            vectors.append(vector)

        return vectors
